#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

from __future__ import annotations

import logging
import traceback
from decimal import Decimal
from time import sleep
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    # to avoid circular import for type checking
    from kraken_infinity_grid.gridbot import KrakenInfinityGridBot

LOG: logging.Logger = logging.getLogger(__name__)


class OrderManager:

    def __init__(self: OrderManager, strategy: KrakenInfinityGridBot) -> None:
        LOG.debug("Initializing the OrderManager...")
        self.__s = strategy

    def add_missed_sell_orders(self: Self) -> None:
        """
        This functions can create sell orders in case there is at least one
        executed buy order that is missing its sell order.

        Missed sell orders came into place when a buy was executed and placing
        the sell failed. An entry to the missed sell order id table is added
        right before placing a sell order.
        """
        LOG.info("- Create sell orders based on unsold buy orders...")
        for entry in self.__s.unsold_buy_order_txids.get():
            LOG.info("  - %s", entry)
            self.handle_arbitrage(
                side="sell",
                order_price=entry["price"],
                txid_id_to_delete=entry["txid"],
            )

    def assign_all_pending_transactions(self: Self) -> None:
        """Assign all pending transactions to the orderbook."""
        LOG.info("- Checking pending transactions...")
        for order in self.__s.pending_txids.get():
            self.assign_order_by_txid(txid=order["txid"])

    def assign_order_by_txid(self: Self, txid: str, tries: int = 1) -> None:
        """
        Assigns an order by its txid to the orderbook.

        - Option 1: Removes them from the pending txids and appends it to
                    the orderbook
        - Option 2: Updates the info of the order in the orderbook

        There is no need for checking the order status, since after the order
        was added to the orderbook, the algorithm will handle any removals in
        case of closed orders.
        """

        LOG.info("Processing %s (try: %d / 10)", txid, tries)
        order_info = self.__s.user.get_orders_info(txid=txid)
        LOG.debug("- Order information: %s", order_info)

        if len(order_info.keys()) != 0:
            order_to_assign = order_info[txid]
            order_to_assign["txid"] = txid
            if self.__s.pending_txids.get(filters={"txid": txid}).all():  # type: ignore[no-untyped-call]
                self.__s.orderbook.add(order_to_assign)
                self.__s.pending_txids.remove(txid)
            else:
                self.__s.orderbook.update(order_to_assign, filters={"txid": txid})
                LOG.info("%s: Updated order in orderbook.", txid)

            LOG.info(
                "Current invested value: %f / %d %s",
                self.__s.investment,
                self.__s.max_investment,
                self.__s.quote_currency,
            )
        else:
            # FIXME: Check if this can still happen.
            LOG.info("%s: order was empty when fetch, try again", txid)
            if tries < 10:
                sleep(1)
                self.assign_order_by_txid(txid=txid, tries=tries + 1)
            else:
                raise ValueError(
                    str(
                        f"{self.__s.symbol}: Could not assign txid, since it "
                        f"was always empty when fetch: {txid}",
                    ),
                )

    # =============================================================================
    #            C H E C K - P R I C E - R A N G E
    # =============================================================================

    def __check_pending_txids(self: OrderManager) -> bool:
        """
        Skip checking the price range, because first all missing orders
        must be assigned. Otherwise this could lead to double trades.

        Returns False if okay and True if ``check_price_range`` must be skipped.
        """
        if self.__s.pending_txids.count() != 0:
            LOG.info("check_price_range... skip because pending_txids != 0")
            self.assign_all_pending_transactions()
            return True
        return False

    def __check_near_buy_orders(self: OrderManager) -> None:
        """
        Cancel buy orders that are next to each other. Only the lowest buy order
        will survive. This is to avoid that the bot buys at the same price
        multiple times.

        Other functions handle the eventual cancellation of a very low buy order
        to avoid falling out of the price range.
        """
        LOG.debug("Checking if distance between buy orders is too low...")

        if len(buy_prices := self.__s.get_current_buy_prices()) == 0:
            return

        buy_prices.sort(reverse=True)
        for i, price in enumerate(buy_prices[1:]):
            if (
                price == buy_prices[i]
                or (buy_prices[i] / price) - 1 < self.__s.interval / 2
            ):
                for order in self.__s.get_active_buy_orders():
                    if order["price"] == buy_prices[i]:
                        self.handle_cancel_order(txid=order["txid"])
                        break

    def __check_n_open_buy_orders(self: OrderManager) -> None:
        """
        Ensures that there are n open buy orders and will place orders until n.

        TODO: Think of placing a batch order to place multiple orders at once.
        """
        LOG.debug(
            "Checking if there are %d open buy orders...",
            self.__s.n_open_buy_orders,
        )
        buy_prices: list[float] = self.__s.get_current_buy_prices()
        active_buy_orders: list[dict] = self.__s.get_active_buy_orders().all()  # type: ignore[no-untyped-call]
        can_place_buy_order: bool = True

        while (
            len(active_buy_orders) < self.__s.n_open_buy_orders
            and can_place_buy_order
            and self.__s.pending_txids.count() == 0
            and not self.__s.max_investment_reached
        ):

            fetched_balances: dict[str, float] = self.__s.get_balances()
            if fetched_balances["quote_available"] > self.__s.amount_per_grid_plus_fee:
                order_price: float = self.__s.get_order_price(
                    side="buy",
                    last_price=(
                        self.__s.ticker.last
                        if len(active_buy_orders) == 0
                        else min(buy_prices)
                    ),
                )

                self.handle_arbitrage(side="buy", order_price=order_price)
                active_buy_orders = self.__s.get_active_buy_orders().all()  # type: ignore[no-untyped-call]
                buy_prices = self.__s.get_current_buy_prices()
                LOG.info("Length of active buy orders: %s", len(active_buy_orders))
            else:
                LOG.warning("Not enough quote currency available to place buy order!")
                can_place_buy_order = False

    def __check_lowest_cancel_of_more_than_n_buy_orders(self: OrderManager) -> None:
        """
        Cancel the lowest buy order if new higher buy was placed because of an
        executed sell order.
        """
        LOG.debug("Checking if the lowest buy order needs to be canceled...")
        buy_prices = self.__s.get_current_buy_prices()
        active_buy_orders = self.__s.get_active_buy_orders().all()  # type: ignore[no-untyped-call]
        while len(buy_prices) > self.__s.n_open_buy_orders:
            for order in active_buy_orders:
                if order["price"] == min(buy_prices):
                    self.handle_cancel_order(txid=order["txid"])
                    buy_prices = self.__s.get_current_buy_prices()

    def __shift_buy_orders_up(self: OrderManager) -> bool:
        """
        Checks if the buy order prices are not to low. If there are too low,
        they get canceled and the ``check_price_range`` function is triggered
        again to place new buy orders.

        Returns ``True`` if the orders get canceled and the
        ``check_price_range`` functions stops.
        """
        LOG.debug("Checking if buy orders need to be shifted up...")
        active_buy_orders = self.__s.get_active_buy_orders().all()  # type: ignore[no-untyped-call]
        if len(active_buy_orders) > 0:
            buy_prices = self.__s.get_current_buy_prices()
            if (
                self.__s.ticker.last
                > max(buy_prices)
                * (1 + self.__s.interval)
                * (1 + self.__s.interval)
                * 1.001
            ):
                self.cancel_all_open_buy_orders()
                self.check_price_range()
                return True

        return False

    def __check_extra_sell_order(self: OrderManager) -> None:
        """
        Checks if an extra sell order can be placed. This only applies for the
        SWING strategy.
        """
        if self.__s.strategy != "SWING":
            return

        LOG.debug("Checking if extra sell order can be placed...")
        active_sell_orders = self.__s.get_active_sell_orders().all()  # type: ignore[no-untyped-call]
        if len(active_sell_orders) == 0:
            fetched_balances = self.__s.get_balances()

            if (
                fetched_balances["base_available"] * self.__s.ticker.last
                > self.__s.amount_per_grid_plus_fee
            ):
                order_price = self.__s.get_order_price(
                    side="sell",
                    last_price=self.__s.ticker.last,
                    extra_sell=True,
                )
                self.__s.t.send_to_telegram(
                    f"ℹ️ {self.__s.symbol}: Placing extra sell order",  # noqa: RUF001
                )
                self.handle_arbitrage(side="sell", order_price=order_price)

    def check_price_range(self: OrderManager) -> None:
        """
        Checks if the orders prices match the conditions of the bot respecting
        the current price.

        If the price (``self.ticker.last``) raises to high, the open buy orders
        will be canceled and new buy orders below the price respecting the
        interval will be placed.
        """
        if self.__s.dry_run:
            LOG.debug("Dry run, not checking price range.")
            return

        LOG.debug("Check conditions for upgrading the grid...")

        if self.__check_pending_txids():
            LOG.debug("Not checking price range because of pending txids.")
            return

        # Remove orders that are next to each other
        self.__check_near_buy_orders()

        # Ensure n open buy orders
        self.__check_n_open_buy_orders()

        # Return if some newly placed order is still pending and not in the
        # orderbook.
        if self.__s.pending_txids.count() != 0:
            return

        # Check if there are more than n buy orders and cancel the lowest
        self.__check_lowest_cancel_of_more_than_n_buy_orders()

        # Check the price range and shift the orders up if required
        if self.__shift_buy_orders_up():
            return

        # Place extra sell order (only for SWING strategy)
        self.__check_extra_sell_order()

    # =============================================================================
    #           C R E A T E / C A N C E L - O R D E R S
    # =============================================================================

    def handle_arbitrage(
        self: Self,
        side: str,
        order_price: float,
        txid_id_to_delete: str | None = None,
    ) -> None:
        """Handles the arbitrage between buy and sell orders."""
        LOG.debug(
            "Handle Arbitrage for %s order with order price: %s and"
            " txid_to_delete: %s",
            side,
            order_price,
            txid_id_to_delete,
        )

        if self.__s.dry_run:
            LOG.info("Dry run, not placing %s order.", side)
            # FIXME: do proper dryrun
            return

        if side == "buy":
            self.new_buy_order(
                order_price=order_price,
                txid_to_delete=txid_id_to_delete,
            )
        elif side == "sell":
            self.new_sell_order(
                order_price=order_price,
                txid_id_to_delete=txid_id_to_delete,
            )
        else:
            raise ValueError(f"Invalid side: {side}")

        # Wait a bit to avoid rate limiting.
        sleep(0.2)

    def new_buy_order(
        self: OrderManager,
        order_price: float,
        txid_to_delete: str | None = None,
    ) -> None:
        """Places a new buy order."""
        if self.__s.dry_run:
            LOG.info("Dry run, not placing buy order.")
            # FIXME: do proper dryrun
            return

        if txid_to_delete is not None:
            self.__s.orderbook.remove(filters={"txid": txid_to_delete})

        if len(self.__s.get_active_buy_orders().all()) >= self.__s.n_open_buy_orders:  # type: ignore[no-untyped-call]
            return

        # Check if algorithm reached the max_investment value
        if self.__s.max_investment_reached:
            return

        current_balances = self.__s.get_balances()

        # Compute the target price for the upcoming buy order.
        order_price = float(
            self.__s.trade.truncate(
                amount=order_price,
                amount_type="price",
                pair=self.__s.symbol,
            ),
        )

        # Compute the target volume for the upcoming buy order.
        volume = float(
            self.__s.trade.truncate(
                amount=Decimal(self.__s.amount_per_grid) / Decimal(order_price),
                amount_type="volume",
                pair=self.__s.symbol,
            ),
        )

        # ======================================================================
        # Check if there is enough quote balance available to place a buy order.
        if current_balances["quote_available"] > self.__s.amount_per_grid_plus_fee:
            LOG.info(
                "Placing order to buy %s %s @ %s %s.",
                volume,
                self.__s.base_currency,
                order_price,
                self.__s.quote_currency,
            )

            # Place a new buy order, append txid to pending list and delete
            # corresponding sell order from local orderbook.
            placed_order = self.__s.trade.create_order(
                ordertype="limit",
                side="buy",
                volume=volume,
                pair=self.__s.symbol,
                price=order_price,
                userref=self.__s.userref,
                validate=self.__s.dry_run,
            )

            self.__s.pending_txids.add(placed_order["txid"][0])
            # if txid_to_delete is not None:
            #     self.__s.orderbook.remove(filters={"txid": txid_to_delete})
            self.__s.om.assign_order_by_txid(placed_order["txid"][0])
            return

        # ======================================================================
        # Not enough available funds to place a buy order.
        message = f"⚠️ {self.__s.symbol}"
        message += f"├ Not enough {self.__s.quote_currency}"
        message += f"├ to buy {volume} {self.__s.base_currency}"
        message += f"└ for {order_price} {self.__s.quote_currency}"
        self.__s.t.send_to_telegram(message)
        LOG.warning("Current balances: %s", current_balances)
        return

    def new_sell_order(  # noqa: C901
        self: OrderManager,
        order_price: float,
        txid_id_to_delete: str | None = None,
    ) -> None:
        """Places a new sell order."""

        if self.__s.strategy == "cDCA":
            LOG.debug("cDCA strategy, not placing sell order.")
            if txid_id_to_delete is not None:
                self.__s.orderbook.remove(filters={"txid": txid_id_to_delete})
            return

        LOG.debug("Check conditions for placing a sell order...")
        fetched_balances = self.__s.get_balances()
        volume: float | None = None

        # ======================================================================
        if txid_id_to_delete is not None:  # If corresponding buy order filled
            # GridSell always has txid_id_to_delete set.

            # Add the txid of the corresponding buy order to the unsold buy
            # order txids in order to ensure that the corresponding sell order
            # will be placed - even if placing now fails.
            if not self.__s.unsold_buy_order_txids.get(
                filters={"txid": txid_id_to_delete},
            ).all():  # type: ignore[no-untyped-call]
                self.__s.unsold_buy_order_txids.add(
                    txid=txid_id_to_delete,
                    price=order_price,
                )

            # ==================================================================
            # Get the corresponding buy order in order to retrieve the volume.
            corresponding_buy_order = self.__s.user.get_orders_info(
                txid=txid_id_to_delete,
            )[txid_id_to_delete]

            # In some cases the corresponding buy order is not closed yet and
            # the vol_exec is missing. In this case, the function will be
            # called again after a short delay.
            if (
                corresponding_buy_order["status"] != "closed"
                or corresponding_buy_order["vol_exec"] == 0
            ):
                LOG.warning(
                    "Can't place sell order, since the corresponding buy order"
                    " is not closed yet. Retry in 1 second. (order: %s)",
                    corresponding_buy_order,
                )
                sleep(1)
                self.__s.om.new_sell_order(
                    order_price=order_price,
                    txid_id_to_delete=txid_id_to_delete,
                )
                return

            if self.__s.strategy == "GridSell":
                # Volume of a GridSell is fixed to the executed volume of the
                # buy order.
                volume = float(
                    self.__s.trade.truncate(
                        amount=float(corresponding_buy_order["vol_exec"]),
                        amount_type="volume",
                        pair=self.__s.symbol,
                    ),
                )

        order_price = float(
            self.__s.trade.truncate(
                amount=order_price,
                amount_type="price",
                pair=self.__s.symbol,
            ),
        )

        if self.__s.strategy in {"GridHODL", "SWING"} or (
            self.__s.strategy == "GridSell" and volume is None
        ):
            # For GridSell: This is only the case if there is no corresponding
            # buy order and the sell order was placed, e.g. due to an extra sell
            # order via selling of partially filled buy orders.

            # Respect the fee to not reduce the quote currency over time, while
            # accumulating the base currency.
            volume = float(
                self.__s.trade.truncate(
                    amount=Decimal(self.__s.amount_per_grid)
                    / (Decimal(order_price) * (1 - (2 * Decimal(self.__s.fee)))),
                    amount_type="volume",
                    pair=self.__s.symbol,
                ),
            )
        # ======================================================================

        # Check if there is enough base currency available for selling.
        if fetched_balances["base_available"] >= volume:
            # Place new sell order, append id to pending list, and delete
            # corresponding buy order from local orderbook.
            LOG.info(
                "Placing order to sell %s %s @ %s %s.",
                volume,
                self.__s.base_currency,
                order_price,
                self.__s.quote_currency,
            )

            placed_order = self.__s.trade.create_order(
                ordertype="limit",
                side="sell",
                volume=volume,
                pair=self.__s.symbol,
                price=order_price,
                userref=self.__s.userref,
                validate=self.__s.dry_run,
            )

            placed_order_txid = placed_order["txid"][0]
            self.__s.pending_txids.add(placed_order_txid)

            if txid_id_to_delete is not None:
                self.__s.orderbook.remove(filters={"txid": txid_id_to_delete})
                self.__s.unsold_buy_order_txids.remove(txid=txid_id_to_delete)

            self.__s.om.assign_order_by_txid(txid=placed_order_txid)
            return

        # ======================================================================
        # Not enough funds to sell
        message = f"⚠️ {self.__s.symbol}"
        message += f"├ Not enough {self.__s.base_currency}"
        message += f"├ to sell {volume} {self.__s.base_currency}"
        message += f"└ for {order_price} {self.__s.quote_currency}"

        self.__s.t.send_to_telegram(message)
        LOG.warning("Current balances: %s", fetched_balances)

        if self.__s.strategy == "GridSell":
            # Restart the algorithm if there is not enough base currency to
            # sell. This could only happen if some orders have not being
            # processed properly, the algorithm is not in sync with the
            # exchange, or manual trades have been made during processing.
            self.__s.save_exit(reason=message)
        elif txid_id_to_delete is not None:
            self.__s.orderbook.remove(filters={"txid": txid_id_to_delete})

    def handle_filled_order_event(
        self: OrderManager,
        txid: str,
    ) -> None:
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
        if (order_details := self.get_orders_info_with_retry(txid=txid)) is None:
            self.__s.save_exit(
                f"Cold not retrieve order info for '{txid}' during"
                " handling a filled order event!",
            )

        # ======================================================================
        # Check if the order belongs to this bot and return if not
        ##
        if (
            order_details["descr"]["pair"] != self.__s.altname
            or order_details["userref"] != self.__s.userref
        ):
            LOG.debug(
                "Filled order %s was not from this bot or pair.",
                txid,
            )
            return

        # ======================================================================
        # Sometimes the order is not closed yet, so retry fetching the order.
        ##
        tries = 1
        while order_details["status"] != "closed" and tries <= 3:
            order_details = self.get_orders_info_with_retry(txid=txid)
            LOG.warning(
                "Order '%s' is not closed! Retry %d/3 in %d seconds...",
                txid,
                tries,
                (wait_time := 2 + tries),
            )
            sleep(wait_time)
            tries += 1

        if order_details["status"] != "closed":
            self.__s.save_exit(
                "handle_filled_order_event - fetched order is not closed!"
                f" {order_details}",
            )

        # ======================================================================
        if self.__s.dry_run:
            LOG.info("Dry run, not handling filled order event.")
            return

        # ======================================================================
        # Notify about the executed order
        ##
        self.__s.t.send_to_telegram(
            message=str(
                f"✅ {self.__s.symbol}: "
                f"{order_details['descr']['type'][0].upper()}{order_details['descr']['type'][1:]} "
                "order executed"
                f"\n ├ Price » {order_details['descr']['price']} {self.__s.quote_currency}"
                f"\n ├ Size » {order_details['vol_exec']} {self.__s.base_currency}"
                f"\n └ Size in {self.__s.quote_currency} » "
                f"{round(float(order_details['descr']['price']) * float(order_details['vol_exec']), self.__s.cost_decimals)}",
            ),
        )

        # ======================================================================
        # Create a sell order for the executed buy order.
        ##
        if order_details["descr"]["type"] == "buy":
            self.handle_arbitrage(
                side="sell",
                order_price=self.__s.get_order_price(
                    side="sell",
                    last_price=float(order_details["descr"]["price"]),
                ),
                txid_id_to_delete=txid,
            )

        # ======================================================================
        # Create a buy order for the executed sell order.
        ##
        elif (
            len(
                [
                    o
                    for o in self.__s.get_active_sell_orders().all()  # type: ignore[no-untyped-call]
                    if o["side"] == "sell" and o["txid"] != txid
                ],
            )
            != 0
        ):
            # A new buy order will only be placed if there is another sell
            # order, because if the last sell order was filled, the price is so
            # high, that all buy orders will be canceled anyway and new buy
            # orders will be placed in ``check_price_range`` during shift-up.
            self.handle_arbitrage(
                side="buy",
                order_price=self.__s.get_order_price(
                    side="buy",
                    last_price=float(order_details["descr"]["price"]),
                ),
                txid_id_to_delete=txid,
            )
        else:
            # Remove filled order from list of all orders
            self.__s.orderbook.remove(filters={"txid": txid})

    def handle_cancel_order(self: OrderManager, txid: str) -> None:
        """
        Cancels an order by txid, removes it from the orderbook, and checks if
        there there was some volume executed which can be sold later.
        """
        LOG.info("Cancelling order: %s", txid)
        try:
            order = self.__s.user.get_orders_info(txid=txid)[txid]
            if order["descr"]["pair"] != self.__s.altname:
                return

            if self.__s.dry_run:
                LOG.info("DRY RUN: Not cancelling order: %s", txid)
                return

            self.__s.trade.cancel_order(txid=txid)
            self.__s.orderbook.remove(filters={"txid": txid})

            # Check if the order has some vol_exec to sell
            ##
            if float(order["vol_exec"]) != float(0):
                LOG.info(
                    "Order %s is partly filled - saving those funds.",
                    txid,
                )
                b = self.__s.configuration.get()

                # Add vol_exec to remaining funds
                updates = {
                    "vol_of_unfilled_remaining": b["vol_of_unfilled_remaining"]
                    + float(order["vol_exec"]),
                }

                # Set new highest buy price.
                if b["vol_of_unfilled_remaining_max_price"] < float(
                    order["descr"]["price"],
                ):
                    updates |= {
                        "vol_of_unfilled_remaining_max_price": float(
                            order["descr"]["price"],
                        ),
                    }
                self.__s.configuration.update(updates)

                # Sell remaining funds if there is enough to place a sell order.
                # Its not perfect but good enough. (Some funds may still be
                # stuck) - but better than nothing.
                b = self.__s.configuration.get()
                if (
                    b["vol_of_unfilled_remaining"]
                    * b["vol_of_unfilled_remaining_max_price"]
                    >= self.__s.amount_per_grid
                ):
                    LOG.info(
                        "Collected enough funds via partly filled buy orders to"
                        " create a new sell order...",
                    )
                    self.handle_arbitrage(
                        side="sell",
                        order_price=self.__s.get_order_price(
                            side="sell",
                            last_price=b["vol_of_unfilled_remaining_max_price"],
                        ),
                    )
                    self.__s.configuration.update(  # Reset the remaining funds
                        {
                            "vol_of_unfilled_remaining": 0,
                            "vol_of_unfilled_remaining_max_price": 0,
                        },
                    )
        except Exception:  # noqa: BLE001
            self.__s.save_exit(
                f"Could not cancel order: {txid}\n {traceback.format_exc()}",
            )

    def cancel_all_open_buy_orders(self: OrderManager) -> None:
        """
        Cancels all open buy orders and removes them from the orderbook.

        TODO: Use batch cancel order
        """
        LOG.info("Cancelling all open buy orders...")
        try:
            for txid, order in self.__s.user.get_open_orders(
                userref=self.__s.userref,
            )["open"].items():
                if (
                    order["descr"]["type"] == "buy"
                    and order["descr"]["pair"] == self.__s.altname
                ):
                    self.handle_cancel_order(txid=txid)
                    sleep(0.2)

            self.__s.orderbook.remove(filters={"side": "buy"})
        except Exception:  # noqa: BLE001
            # FIXME: Check if this can still happen. Can't remember why this
            #        was added.
            self.__s.save_exit(
                str(
                    f"❌ Error in function >cancelAllOpenBuyOrders < \n"
                    " !!!--> MAYBE OPEN BUY ORDERS ARE STILL ACTIVE <--!!!"
                    f" exit()\n {traceback.format_exc()}",
                ),
            )

    def get_orders_info_with_retry(
        self: OrderManager,
        txid: str,
        tries: int = 0,
        max_tries: int = 3,
    ) -> dict | None:
        """
        Returns the order details for a given txid.

        NOTE: We need retry here, since Kraken lacks of fast processing of
              filled orders and making them available via REST API.
        TODO: Maybe add to missed buy/sell instead of retry and exit?
        """
        while tries <= max_tries and not (
            order_details := self.__s.user.get_orders_info(
                txid=txid,
            ).get(txid)
        ):
            LOG.warning(
                "Could not find order '%s'. Retry %d/3 in %d seconds...",
                txid,
                tries,
                (wait_time := 2 + tries),
            )
            sleep(wait_time)
            tries += 1

        return order_details  # type: ignore[no-any-return]
