# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

# FIXME: Address pylint issues with too many arguments, not applicable in this
#        project context.

import traceback
from abc import abstractmethod
from datetime import datetime
from decimal import Decimal
from logging import getLogger
from time import sleep
from types import SimpleNamespace
from typing import Self

from kraken.exceptions import KrakenUnknownOrderError
from pydantic import BaseModel

from kraken_infinity_grid.core.event_bus import Event, EventBus
from kraken_infinity_grid.core.state_machine import StateMachine, States
from kraken_infinity_grid.exceptions import GridBotStateError
from kraken_infinity_grid.infrastructure.database import (
    Configuration,
    Orderbook,
    PendingTXIDs,
    UnsoldBuyOrderTXIDs,
)
from kraken_infinity_grid.interfaces.exchange import IExchangeRESTService
from kraken_infinity_grid.interfaces.strategy import IStrategy
from kraken_infinity_grid.models.dto.configuration import BotConfigDTO
from kraken_infinity_grid.models.schemas.exchange import (
    AssetPairInfoSchema,
    OrderInfoSchema,
)
from kraken_infinity_grid.services import OrderbookService
from kraken_infinity_grid.models.schemas.exchange import OrderInfoListSchema

LOG = getLogger(__name__)


class GridStrategyRuntimeAttributesDTO(BaseModel):
    """
    Custom attributes for grid strategies that are evaluated during
    runtime.
    """

    altname: str  # e.g. "XBTZEUR"
    symbol: str  # 'wsname' on kraken e.g. "XBT/EUR"
    cost_decimals: int
    xbase_currency: str  # base currency e.g. "XXBT"
    zquote_currency: str  # quote currency e.g. "ZEUR"
    amount_per_grid_plus_fee: float


class IGridBaseStrategy(IStrategy):
    """Base interface for grid-based trading strategies."""

    def __init__(
        self,
        config: BotConfigDTO,
        rest_api: IExchangeRESTService,
        orderbook_service: OrderbookService,
        event_bus: EventBus,
        state_machine: StateMachine,
        configuration_table: Configuration,
        orderbook_table: Orderbook,
        pending_txids_table: PendingTXIDs,
        unsold_buy_order_txids_table: UnsoldBuyOrderTXIDs,
    ) -> None:
        self._config = config
        self._rest_api = rest_api
        self._event_bus = event_bus
        self._orderbook_service = orderbook_service
        self._state_machine = state_machine
        self._configuration_table = configuration_table
        self._orderbook_table = orderbook_table
        self._pending_txids_table = pending_txids_table
        self._unsold_buy_order_txids_table = unsold_buy_order_txids_table
        self._ticker: SimpleNamespace = None
        self._runtime_attrs: GridStrategyRuntimeAttributesDTO = None

    # ==========================================================================
    # Event handlers
    # FIXME: events should have basemodel class with data attribute
    def on_ticker_update(self, event: Event) -> None:
        if event.data["symbol"] != self._config.symbol:
            # The grid strategy is only interested in ticker updates for its
            # symbol.
            return

        self._ticker = SimpleNamespace(last=event.data["last"])
        self._configuration_table.update({"last_price_time": datetime.now()})

        # FIXME: only if init done
        if self._state_machine.state == States.RUNNING:
            if self._unsold_buy_order_txids_table.count() != 0:
                self._orderbook_service.add_missed_sell_orders()

            self.__check_price_range()

    def on_order_placed(self, event: Event) -> None:
        LOG.debug("Got order_placed event: %s", event.data)
        self._orderbook_service.assign_order_by_txid(event.data["order_id"])

    def on_order_filled(self, event: Event) -> None:
        LOG.debug("Got order_filled event: %s", event.data)
        self._orderbook_service.handle_filled_order_event(event.data["order_id"])

    def on_order_cancelled(self, event: Event) -> None:
        LOG.debug("Got order_cancelled event: %s", event.data)
        self._orderbook_service.handle_cancel_order(event.data["order_id"])

    def on_prepare_for_trading(self, event: Event) -> None:
        """
        This function gets triggered once during the setup of the algorithm. It
        prepares the algorithm for live trading by checking the asset pair
        parameters, syncing the local with the upstream orderbook, place missing
        sell orders that not get through because of e.g. "missing funds", and
        updating the orderbook.

        This function must be sync, since it must block until the setup is done.
        """
        LOG.info(
            "Preparing for trading by initializing and updating local orderbook...",
        )

        self._event_bus.publish(
            "notification",
            {"message": f"✅ {self._config.name} is starting!"},
        )

        # ======================================================================

        # Check the fee and altname of the asset pair
        ##
        self.__retrieve_asset_information()

        # Append orders to local orderbook in case they are not saved yet
        ##
        self._orderbook_service.assign_all_pending_transactions()

        # Try to place missing sell orders that not get through because
        # of "missing funds".
        ##
        self.__add_missed_sell_orders()

        # Update the orderbook, check for closed, filled, cancelled trades,
        # and submit new orders if necessary.
        ##

        try:
            self.__update_order_book()
        except Exception as exc:
            message = f"Exception while updating the orderbook: {exc}: {traceback.format_exc()}"
            LOG.error(message)
            self._state_machine.transition_to(States.ERROR)
            raise GridBotStateError(message) from exc

        # Check if the configured amount per grid or the interval have changed,
        # requiring a cancellation of all open buy orders.
        ##
        self.__check_configuration_changes()

        # Everything is done, the bot is ready to trade live.
        ##
        self._state_machine.facts["ready_to_trade"] = True
        LOG.info("Algorithm is ready to trade!")

        # Checks if the open orders match the range and cancel if necessary. It
        # is the heart of this algorithm and gets triggered every time the price
        # changes.
        ##
        self.__check_price_range()
        self._state_machine.transition_to(States.RUNNING)

    # ==========================================================================
    # Setup methods

    def __retrieve_asset_information(self: Self) -> None:
        """Check the asset pair information."""
        LOG.info("- Retrieving asset pair information...")
        pair_info: AssetPairInfoSchema = self._rest_api.get_asset_pair_info(
            pair=self._config.symbol.replace("/", ""),
        )
        LOG.debug(pair_info)

        if self._config.fee is None:
            # This is the case if the '--fee' parameter was not passed, then we
            # take the highest maker fee.
            self._config.fee = float(pair_info.fees_maker[0][1]) / 100

        # Setup runtime attributes derived from asset pair info
        self._runtime_attrs = GridStrategyRuntimeAttributesDTO(
            altname=pair_info.altname,  # e.g. XBTZEUR
            symbol=pair_info.wsname,  # e.g. XBT/EUR
            cost_decimals=pair_info.cost_decimals,
            xbase_currency=pair_info.base,  # e.g. XXBT
            zquote_currency=pair_info.quote,  # e.g. ZEUR
            amount_per_grid_plus_fee=self._config.amount_per_grid
            * (1 + self._config.fee),
        )

    def __update_orderbook_get_open_orders(self: Self) -> list[OrderInfoSchema]:
        """Get the open orders and txid as lists."""
        LOG.info("  - Retrieving open orders from upstream...")

        open_orders = []
        for order in self._rest_api.get_open_orders(userref=self._config.userref):
            if order.pair == self._runtime_attrs.altname:
                open_orders.append(order)
        return open_orders

    def __update_order_book_handle_closed_order(self: Self, closed_order: dict) -> None:
        """
        Gets executed when an order of the local orderbook was closed in the
        upstream orderbook during the ``update_orderbook`` function in the init
        of the algorithm.

        This function triggers the Notification message of the executed order and
        places a new order.

        FIXME: closed order must be a pydantic model, not a dict.
        """
        LOG.info("Handling executed order: %s", closed_order["txid"])
        closed_order["side"] = closed_order["descr"]["type"]

        message = str(
            f"✅ {self._runtime_attrs.symbol}: {closed_order['side'][0].upper()}{closed_order['side'][1:]} "
            "order executed"
            f"\n ├ Price » {closed_order['price']} {self._config.quote_currency}"
            f"\n ├ Size » {closed_order['vol_exec']} {self._config.base_currency}"
            f"\n └ Size in {self._config.quote_currency} » "
            f"{float(closed_order['price']) * float(closed_order['vol_exec'])}",
        )

        self._event_bus.publish("notification", {"message": message})
        # ======================================================================
        # If a buy order was filled, the sell order needs to be placed.
        if closed_order["side"] == "buy":
            self.handle_arbitrage(
                side="sell",
                order_price=self._get_order_price(
                    side="sell",
                    last_price=float(closed_order["price"]),
                ),
                txid_to_delete=closed_order["txid"],
            )

        # ======================================================================
        # If a sell order was filled, we may need to place a new buy order.
        elif closed_order["side"] == "sell":
            # A new buy order will only be placed if there is another sell
            # order, because if the last sell order was filled, the price is so
            # high, that all buy orders will be canceled anyway and new buy
            # orders will be placed in ``check_price_range`` during shift-up.
            if (
                self._orderbook_table.count(
                    filters={"side": "sell"},
                    exclude={"txid": closed_order["txid"]},
                )
                != 0
            ):
                self._orderbook_service.handle_arbitrage(
                    side="buy",
                    order_price=self._get_order_price(
                        side="buy",
                        last_price=float(closed_order["price"]),
                    ),
                    txid_to_delete=closed_order["txid"],
                )
            else:
                self._orderbook_table.remove(filters={"txid": closed_order["txid"]})

    def __update_order_book(self: Self) -> None:
        """
        This function only gets triggered once during the setup of the
        algorithm.

        It checks:
        - ... if the orderbook is up to date, remove filled, closed, and
          canceled orders.
        - ... the local orderbook for changes - comparison with upstream
          orderbook
        - ... and will place new orders if filled.
        """
        LOG.info("- Syncing the orderbook with upstream...")

        # ======================================================================
        # Only track orders that belong to this instance.
        ##
        open_orders: list[OrderInfoSchema] = self.__update_orderbook_get_open_orders()
        open_txids: list[str] = [order.txid for order in open_orders]

        # ======================================================================
        # Orders of the upstream which are not yet tracked in the local
        # orderbook will now be added to the local orderbook.
        ##
        local_txids = [order["txid"] for order in self._orderbook_table.get_orders()]
        something_changed = False
        for order in open_orders:
            if order.txid not in local_txids:
                LOG.info(
                    "  - Adding upstream order to local orderbook: %s",
                    order.txid,
                )
                self._orderbook_table.add(order)
                something_changed = True
        if not something_changed:
            LOG.info("  - Nothing changed!")

        # ======================================================================
        # Check all orders of the local orderbook against those from upstream.
        # If they got filled -> place new orders.
        # If canceled -> remove from local orderbook.
        ##
        for order in self._orderbook_table.get_orders():
            if order["txid"] not in open_txids:
                closed_order: OrderInfoSchema = (
                    self._orderbook_service.get_orders_info_with_retry(
                        txid=order["txid"]
                    )
                )
                # ==============================================================
                # Order was filled
                if closed_order.status == "closed":
                    self.__update_order_book_handle_closed_order(
                        closed_order=closed_order,
                    )

                # ==============================================================
                # Order was closed
                elif closed_order.status in {"canceled", "expired"}:
                    self._orderbook_table.remove(filters={"txid": order["txid"]})

                else:
                    # pending || open order - still active
                    ##
                    continue

        # There are no more filled/closed and cancelled orders in the local
        # orderbook and all upstream orders are tracked locally.
        LOG.info("- Orderbook initialized!")

    def __check_configuration_changes(self: Self) -> None:
        """
        Checking if the database content match with the setup parameters.

        Checking if the order size or the interval have changed, requiring
        all open buy orders to be cancelled.
        """
        LOG.info("- Checking configuration changes...")
        cancel_all_orders = False

        if (
            self._config.amount_per_grid
            != self._configuration_table.get()["amount_per_grid"]
        ):
            LOG.info(" - Amount per grid changed => cancel open buy orders soon...")
            self._configuration_table.update(
                {"amount_per_grid": self._config.amount_per_grid},
            )
            cancel_all_orders = True

        if self._config.interval != self._configuration_table.get()["interval"]:
            LOG.info(" - Interval changed => cancel open buy orders soon...")
            self._configuration_table.update({"interval": self._config.interval})
            cancel_all_orders = True

        if cancel_all_orders:
            self.__cancel_all_open_buy_orders()

        LOG.info("- Configuration checked and up-to-date!")

    # ==========================================================================
    # Kinda main
    def __check_price_range(self: Self) -> None:
        """
        Checks if the orders prices match the conditions of the bot respecting
        the current price.

        If the price (``self.ticker.last``) raises to high, the open buy orders
        will be canceled and new buy orders below the price respecting the
        interval will be placed.
        """
        if self._config.dry_run:
            LOG.debug("Dry run, not checking price range.")
            return

        LOG.debug("Check conditions for upgrading the grid...")

        if self._orderbook_service.check_pending_txids():
            LOG.debug("Not checking price range because of pending txids.")
            return

        # Remove orders that are next to each other
        self.__check_near_buy_orders()

        # Ensure n open buy orders
        self.__check_n_open_buy_orders()

        # Return if some newly placed order is still pending and not in the
        # orderbook.
        if self._pending_txids_table.count() != 0:
            return

        # Check if there are more than n buy orders and cancel the lowest
        self.__check_lowest_cancel_of_more_than_n_buy_orders()

        # Check the price range and shift the orders up if required
        if self.__shift_buy_orders_up():
            return

        # Place extra sell order (only for SWING strategy)
        self._check_extra_sell_order()

    def _get_balances(self: Self) -> dict[str, float]:
        """
        Returns the available and overall balances of the quote and base
        currency.

        FIXME: Is there a way to get the balances of the asset pair directly?
        """
        LOG.debug("Retrieving the user's balances...")

        base_balance = Decimal(0)
        base_available = Decimal(0)
        quote_balance = Decimal(0)
        quote_available = Decimal(0)

        for balance in self._rest_api.get_balances():
            if balance.symbol == self.zbase_currency:
                base_balance = Decimal(balance.balance)
                base_available = base_balance - Decimal(balance.hold_trade)
            elif balance.symbol == self.xquote_currency:
                quote_balance = Decimal(balance.balance)
                quote_available = quote_balance - Decimal(balance.hold_trade)

        balances = {
            "base_balance": float(base_balance),
            "quote_balance": float(quote_balance),
            "base_available": float(base_available),
            "quote_available": float(quote_available),
        }
        LOG.debug("Retrieved balances: %s", balances)
        return balances

    # ==========================================================================
    #           C R E A T E / C A N C E L - O R D E R S
    # ==========================================================================
    def __add_missed_sell_orders(self: Self) -> None:
        """
        This functions can create sell orders in case there is at least one
        executed buy order that is missing its sell order.

        Missed sell orders came into place when a buy was executed and placing
        the sell failed. An entry to the missed sell order id table is added
        right before placing a sell order.
        """
        LOG.info("- Create sell orders based on unsold buy orders...")
        for entry in self._unsold_buy_order_txids_table.get():
            LOG.info("  - %s", entry)
            self.handle_arbitrage(
                side="sell",
                order_price=entry["price"],
                txid_to_delete=entry["txid"],
            )

    def __check_near_buy_orders(self: Self) -> None:
        """
        Cancel buy orders that are next to each other. Only the lowest buy order
        will survive. This is to avoid that the bot buys at the same price
        multiple times.

        Other functions handle the eventual cancellation of a very low buy order
        to avoid falling out of the price range.
        """
        LOG.debug("Checking if distance between buy orders is too low...")

        if (
            len(buy_prices := list(self._orderbook_service.get_current_buy_prices()))
            == 0
        ):
            return

        buy_prices.sort(reverse=True)
        for i, price in enumerate(buy_prices[1:]):
            if (
                price == buy_prices[i]
                or (buy_prices[i] / price) - 1 < self._config.interval / 2
            ):
                for order in self._orderbook_table.get_orders(filters={"side": "buy"}):
                    if order["price"] == buy_prices[i]:
                        self._handle_cancel_order(txid=order["txid"])
                        break

    def __check_n_open_buy_orders(self: Self) -> None:
        """
        Ensures that there are n open buy orders and will place orders until n.
        """
        LOG.debug(
            "Checking if there are %d open buy orders...",
            self._config.n_open_buy_orders,
        )
        can_place_buy_order: bool = True
        buy_prices: list[float] = list(self._orderbook_service.get_current_buy_prices())

        while (
            (
                n_active_buy_orders := self._orderbook_table.count(
                    filters={"side": "buy"},
                )
            )
            < self._config.n_open_buy_orders
            and can_place_buy_order
            and self._pending_txids_table.count() == 0
            and not self._orderbook_service.max_investment_reached
        ):
            fetched_balances: dict[str, float] = self._get_balances()
            if (
                fetched_balances["quote_available"]
                > self._runtime_attrs.amount_per_grid_plus_fee
            ):
                order_price: float = self._get_order_price(
                    side="buy",
                    last_price=(
                        self._ticker.last
                        if n_active_buy_orders == 0
                        else min(buy_prices)
                    ),
                )

                self.handle_arbitrage(side="buy", order_price=order_price)
                buy_prices = list(self._orderbook_service.get_current_buy_prices())
                LOG.debug("Length of active buy orders: %s", n_active_buy_orders + 1)
            else:
                LOG.warning("Not enough quote currency available to place buy order!")
                can_place_buy_order = False

    def __check_lowest_cancel_of_more_than_n_buy_orders(self: Self) -> None:
        """
        Cancel the lowest buy order if new higher buy was placed because of an
        executed sell order.
        """
        LOG.debug("Checking if the lowest buy order needs to be canceled...")

        if (
            n_to_cancel := (
                self._orderbook_table.count(filters={"side": "buy"})
                - self._config.n_open_buy_orders
            )
        ) > 0:
            for order in self._orderbook_table.get_orders(
                filters={"side": "buy"},
                order_by=("price", "asc"),
                limit=n_to_cancel,
            ):
                self._handle_cancel_order(txid=order["txid"])

    def __cancel_all_open_buy_orders(self: Self) -> None:
        """
        Cancels all open buy orders and removes them from the orderbook.
        """
        LOG.info("Cancelling all open buy orders...")
        for order in self._rest_api.get_open_orders(userref=self._config.userref):
            if order.type == "buy" and order.pair == self._runtime_attrs.altname:
                self._handle_cancel_order(txid=order.txid)
                sleep(0.2)  # Avoid rate limiting

        self._orderbook_table.remove(filters={"side": "buy"})

    def __shift_buy_orders_up(self: Self) -> bool:
        """
        Checks if the buy order prices are not to low. If there are too low,
        they get canceled and the ``check_price_range`` function is triggered
        again to place new buy orders.

        Returns ``True`` if the orders get canceled and the
        ``check_price_range`` functions stops.
        """
        LOG.debug("Checking if buy orders need to be shifted up...")

        if (
            max_buy_order := self._orderbook_table.get_orders(
                filters={"side": "buy"},
                order_by=("price", "desc"),
                limit=1,
            ).first()  # type: ignore[no-untyped-call]
        ) and (
            self._ticker.last
            > max_buy_order["price"]
            * (1 + self._config["interval"])
            * (1 + self._config["interval"])
            * 1.001
        ):
            self.__cancel_all_open_buy_orders()
            self.__check_price_range()
            return True

        return False

    def handle_arbitrage(
        self: Self,
        side: str,
        order_price: float,
        txid_to_delete: str | None = None,
    ) -> None:
        """
        Handles the arbitrage between buy and sell orders.

        The existence of this function is mainly justified due to the sleep
        statement at the end.
        """
        LOG.debug(
            "Handle arbitrage for %s order with order price: %s and"
            " txid_to_delete: %s",
            side,
            order_price,
            txid_to_delete,
        )

        if self._config["dry_run"]:
            LOG.info("Dry run, not placing %s order.", side)
            return

        if side == "buy":
            self.new_buy_order(
                order_price=order_price,
                txid_to_delete=txid_to_delete,
            )
        elif side == "sell":
            self._new_sell_order(
                order_price=order_price,
                txid_to_delete=txid_to_delete,
            )

        # Wait a bit to avoid rate limiting.
        sleep(0.2)

    def new_buy_order(
        self: Self,
        order_price: float,
        txid_to_delete: str | None = None,
    ) -> None:
        """Places a new buy order."""
        if self._config["dry_run"]:
            LOG.info("Dry run, not placing buy order.")
            return

        if txid_to_delete is not None:
            self._orderbook_table.remove(filters={"txid": txid_to_delete})

        if (
            self._orderbook_table.count(filters={"side": "buy"})
            >= self._config.n_open_buy_orders
        ):
            # Don't place new buy orders if there are already enough
            return

        # Check if algorithm reached the max_investment value
        if self._config["max_investment_reached"]:
            return

        # Compute the target price for the upcoming buy order.
        order_price = float(
            self._rest_api.truncate(
                amount=order_price,
                amount_type="price",
                pair=self._runtime_attrs.symbol,
            ),
        )

        # Compute the target volume for the upcoming buy order.
        # NOTE: The fee is respected while placing the sell order
        volume = float(
            self._rest_api.truncate(
                amount=Decimal(self._config["amount_per_grid"]) / Decimal(order_price),
                amount_type="volume",
                pair=self._runtime_attrs.symbol,
            ),
        )

        # ======================================================================
        # Check if there is enough quote balance available to place a buy order.
        current_balances = self._get_balances()
        if (
            current_balances["quote_available"]
            > self._runtime_attrs.amount_per_grid_plus_fee
        ):
            LOG.info(
                "Placing order to buy %s %s @ %s %s.",
                volume,
                self._config.base_currency,
                order_price,
                self._config.quote_currency,
            )

            # Place a new buy order, append txid to pending list and delete
            # corresponding sell order from local orderbook.
            placed_order = self._rest_api.create_order(
                ordertype="limit",
                side="buy",
                volume=volume,
                pair=self._runtime_attrs.symbol,
                price=order_price,
                userref=self._config.userref,
                validate=self._config.dry_run,
                oflags="post",  # post-only buy orders
            )

            self._pending_txids_table.add(placed_order["txid"][0])
            self._orderbook_service.om.assign_order_by_txid(placed_order["txid"][0])
            return

        # ======================================================================
        # Not enough available funds to place a buy order.
        message = f"⚠️ {self._runtime_attrs.symbol}"
        message += f"├ Not enough {self._config.quote_currency}"
        message += f"├ to buy {volume} {self._config.base_currency}"
        message += f"└ for {order_price} {self._config.quote_currency}"
        self._event_bus.publish("notification", {"message": message})
        LOG.warning("Current balances: %s", current_balances)

    def handle_filled_order_event(self: Self, txid: str) -> None:
        """
        Gets triggered by a filled order event from the ``on_message`` function.

        It fetches the filled order info (using some tries).

        If there is the KeyError which happens due to Krakens shitty, then wait
        for one second and this function will call it self again and return.
        """
        LOG.debug("Handling a new filled order event for txid: %s", txid)

        # ======================================================================
        # Fetch the order details for the given txid.
        ##
        order_details: OrderInfoSchema = (
            self._orderbook_service.get_orders_info_with_retry(txid=txid)
        )

        # ======================================================================
        # Check if the order belongs to this bot and return if not
        ##
        if (
            order_details.pair != self._runtime_attrs.altname
            or order_details.userref != self._config.userref
        ):
            LOG.debug(
                "Filled order %s was not from this bot or pair.",
                txid,
            )
            return

        # ======================================================================
        # Sometimes the order is not closed yet, so retry fetching the order.
        # FIXME: can't this be done in orderbook_service?
        ##
        tries = 1
        while order_details.status != "closed" and tries <= 3:
            order_details: OrderInfoSchema = (
                self._orderbook_service.get_orders_info_with_retry(
                    txid=txid,
                    exit_on_fail=False,
                )
            )
            LOG.warning(
                "Order '%s' is not closed! Retry %d/3 in %d seconds...",
                txid,
                tries,
                (wait_time := 2 + tries),
            )
            sleep(wait_time)
            tries += 1

        if order_details.status != "closed":
            LOG.warning(
                "Can not handle filled order, since the fetched order is not"
                " closed in upstream!"
                " This may happen due to Kraken's websocket API being faster"
                " than their REST backend. Retrying in a few seconds...",
            )
            self.handle_filled_order_event(txid=txid)
            return

        # ======================================================================
        if self._config.dry_run:
            LOG.info("Dry run, not handling filled order event.")
            return

        # ======================================================================
        # Notify about the executed order
        ##
        self._event_bus.publish(
            "notification",
            {
                "message": str(
                    f"✅ {self._runtime_attrs.symbol}: "
                    f"{order_details.type[0].upper()}{order_details.type[1:]} "
                    "order executed"
                    f"\n ├ Price » {order_details.price} {self._config.quote_currency}"
                    f"\n ├ Size » {order_details.vol_exec} {self._config.base_currency}"
                    f"\n └ Size in {self._config.quote_currency} » "
                    f"{round(order_details.price * order_details.vol_exec, self._runtime_attrs.cost_decimals)}",
                ),
            },
        )

        # ======================================================================
        # Create a sell order for the executed buy order.
        ##
        if order_details.type == "buy":
            self.handle_arbitrage(
                side="sell",
                order_price=self._get_order_price(
                    side="sell",
                    last_price=order_details.price,
                ),
                txid_to_delete=txid,
            )

        # ======================================================================
        # Create a buy order for the executed sell order.
        ##
        elif (
            self._orderbook_table.count(
                filters={"side": "sell"},
                exclude={"txid": txid},
            )
            != 0
        ):
            # A new buy order will only be placed if there is another sell
            # order, because if the last sell order was filled, the price is so
            # high, that all buy orders will be canceled anyway and new buy
            # orders will be placed in ``check_price_range`` during shift-up.
            self.handle_arbitrage(
                side="buy",
                order_price=self._get_order_price(
                    side="buy",
                    last_price=order_details.price,
                ),
                txid_to_delete=txid,
            )
        else:
            # Remove filled order from list of all orders
            self._orderbook_table.remove(filters={"txid": txid})

    def _handle_cancel_order(self: Self, txid: str) -> None:
        """
        Cancels an order by txid, removes it from the orderbook, and checks if
        there there was some volume executed which can be sold later.

        NOTE: The orderbook is the "gate keeper" of this function. If the order
              is not present in the local orderbook, nothing will happen.

        For post-only buy orders - if these were cancelled by Kraken, they are
        still in the local orderbook and will be handled just like regular calls
        of the handle_cancel_order of the algorithm.

        For orders that were cancelled by the algorithm, these will cancelled
        via API and removed from the orderbook. The incoming "canceled" message
        by the websocket will be ignored, as the order is already removed from
        the orderbook.

        """
        if self._orderbook_table.count(filters={"txid": txid}) == 0:
            return

        order_details: OrderInfoSchema = (
            self._orderbook_service.get_orders_info_with_retry(txid=txid)
        )

        if (
            order_details.pair != self._runtime_attrs.altname
            or order_details.userref != self._config.userref
        ):
            return

        if self._config.dry_run:
            LOG.info("DRY RUN: Not cancelling order: %s", txid)
            return

        LOG.info("Cancelling order: '%s'", txid)

        try:
            self._rest_api.cancel_order(txid=txid)
        except KrakenUnknownOrderError:
            LOG.info(
                "Order '%s' is already closed. Removing from orderbook...",
                txid,
            )

        self._orderbook_table.remove(filters={"txid": txid})

        # Check if the order has some vol_exec to sell
        ##
        if order_details.vol_exec != 0.0:
            LOG.info(
                "Order '%s' is partly filled - saving those funds.",
                txid,
            )
            b = self._configuration_table.get()

            # Add vol_exec to remaining funds
            updates = {
                "vol_of_unfilled_remaining": b["vol_of_unfilled_remaining"]
                + order_details.vol_exec,
            }

            # Set new highest buy price.
            if b["vol_of_unfilled_remaining_max_price"] < order_details.price:
                updates |= {"vol_of_unfilled_remaining_max_price": order_details.price}
            self._configuration_table.update(updates)

            # Sell remaining funds if there is enough to place a sell order.
            # Its not perfect but good enough. (Some funds may still be
            # stuck) - but better than nothing.
            b = self._configuration_table.get()
            if (
                b["vol_of_unfilled_remaining"]
                * b["vol_of_unfilled_remaining_max_price"]
                >= self._config.amount_per_grid
            ):
                LOG.info(
                    "Collected enough funds via partly filled buy orders to"
                    " create a new sell order...",
                )
                self.handle_arbitrage(
                    side="sell",
                    order_price=self._get_order_price(
                        side="sell",
                        last_price=b["vol_of_unfilled_remaining_max_price"],
                    ),
                )
                self._configuration_table.update(  # Reset the remaining funds
                    {
                        "vol_of_unfilled_remaining": 0,
                        "vol_of_unfilled_remaining_max_price": 0,
                    },
                )

    def build_update_message() -> str:
        """Build a message for updates."""
        balances = self.__s.get_balances()

        message = f"👑 {self.__s.symbol}\n"
        message += f"└ Price » {self.__s.ticker.last} {self.__s.quote_currency}\n\n"

        message += "⚜️ Account\n"
        message += f"├ Total {self.__s.base_currency} » {balances['base_balance']}\n"
        message += f"├ Total {self.__s.quote_currency} » {balances['quote_balance']}\n"
        message += (
            f"├ Available {self.__s.quote_currency} » {balances['quote_available']}\n"
        )
        message += f"├ Available {self.__s.base_currency} » {balances['base_available'] - float(self.__s.configuration.get()['vol_of_unfilled_remaining'])}\n"  # noqa: E501
        message += f"├ Unfilled surplus of {self.__s.base_currency} » {self.__s.configuration.get()['vol_of_unfilled_remaining']}\n"  # noqa: E501
        message += f"├ Wealth » {round(balances['base_balance'] * self.__s.ticker.last + balances['quote_balance'], self.__s.cost_decimals)} {self.__s.quote_currency}\n"  # noqa: E501
        message += f"└ Investment » {round(self.__s.investment, self.__s.cost_decimals)} / {self.__s.max_investment} {self.__s.quote_currency}\n\n"  # noqa: E501

        message += "💠 Orders\n"
        message += f"├ Amount per Grid » {self.__s.amount_per_grid} {self.__s.quote_currency}\n"
        message += f"└ Open orders » {self.__s.orderbook.count()}\n"

        message += "\n```\n"
        message += f" 🏷️ Price in {self.__s.quote_currency}\n"
        max_orders_to_list: int = 5

        next_sells = [
            order["price"]
            for order in self.__s.orderbook.get_orders(
                filters={"side": "sell"},
                order_by=("price", "ASC"),
                limit=max_orders_to_list,
            )
        ]
        next_sells.reverse()

        if (n_sells := len(next_sells)) == 0:
            message += f"└───┬> {self.__s.ticker.last}\n"
        else:
            for index, sell_price in enumerate(next_sells):
                change = (sell_price / self.__s.ticker.last - 1) * 100
                if index == 0:
                    message += f" │  ┌[ {sell_price} (+{change:.2f}%)\n"
                elif index <= n_sells - 1 and index != max_orders_to_list:
                    message += f" │  ├[ {sell_price} (+{change:.2f}%)\n"
            message += f" └──┼> {self.__s.ticker.last}\n"

        next_buys = [
            order["price"]
            for order in self.__s.orderbook.get_orders(
                filters={"side": "buy"},
                order_by=("price", "DESC"),
                limit=max_orders_to_list,
            )
        ]
        if (n_buys := len(next_buys)) != 0:
            for index, buy_price in enumerate(next_buys):
                change = (buy_price / self.__s.ticker.last - 1) * 100
                if index < n_buys - 1 and index != max_orders_to_list:
                    message += f"    ├[ {buy_price} ({change:.2f}%)\n"
                else:
                    message += f"    └[ {buy_price} ({change:.2f}%)"
        message += "\n```"

        self._event_bus.publish("notification", {"message": message})
        self.__s.configuration.update({"last_telegram_update": datetime.now()})

    # ==========================================================================
    # Abstract methods
    @abstractmethod
    def _get_order_price(
        self,
        side: str,
        last_price: float,
        extra_sell: bool = False,
    ) -> float:  # pragma: no cover
        """
        Returns the order price for the next buy or sell order.

        This method should be implemented by the concrete strategy classes.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")

    @abstractmethod
    def _check_extra_sell_order(self: Self) -> None:
        """
        Checks if an extra sell order can be placed. This only applies for the
        SWING strategy.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")

    @abstractmethod
    def _new_sell_order(
        self: Self,
        order_price: float,
        txid_to_delete: str | None = None,
    ) -> None:
        """
        Places a new sell order.

        This method should be implemented by the concrete strategy classes.
        """
        raise NotImplementedError("This method should be implemented by subclasses.")
