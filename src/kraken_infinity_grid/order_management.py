#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

""" Order management for the Kraken Infinity Grid Bot. """

from __future__ import annotations

import logging
from decimal import Decimal
from time import sleep
from typing import TYPE_CHECKING, Self

from kraken.exceptions import KrakenUnknownOrderError

if TYPE_CHECKING:
    # To avoid circular import for type checking
    from kraken_infinity_grid.gridbot import KrakenInfinityGridBot

LOG: logging.Logger = logging.getLogger(__name__)


class OrderManager:
    """Manages the orderbook and the order handling."""

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
                txid_to_delete=entry["txid"],
            )

    def assign_all_pending_transactions(self: Self) -> None:
        """Assign all pending transactions to the orderbook."""
        LOG.info("- Checking pending transactions...")
        for order in self.__s.pending_txids.get():
            self.assign_order_by_txid(txid=order["txid"])

    def assign_order_by_txid(self: Self, txid: str) -> None:
        """
        Assigns an order by its txid to the orderbook.

        - Option 1: Removes them from the pending txids and appends it to
                    the orderbook
        - Option 2: Updates the info of the order in the orderbook

        There is no need for checking the order status, since after the order
        was added to the orderbook, the algorithm will handle any removals in
        case of closed orders.
        """
        LOG.info("Processing '%s' ...", txid)
        order_details = self.get_orders_info_with_retry(txid=txid)
        LOG.debug("- Order information: %s", order_details)

        if (
            order_details["descr"]["pair"] != self.__s.altname
            or order_details["userref"] != self.__s.userref
        ):
            LOG.info("Order '%s' does not belong to this instance.", txid)
            return

        if self.__s.pending_txids.count(filters={"txid": order_details["txid"]}) != 0:
            self.__s.orderbook.add(order_details)
            self.__s.pending_txids.remove(order_details["txid"])
        else:
            self.__s.orderbook.update(
                order_details,
                filters={"txid": order_details["txid"]},
            )
            LOG.info("Updated order '%s' in orderbook.", order_details["txid"])

        LOG.info(
            "Current invested value: %f / %d %s",
            self.__s.investment,
            self.__s.max_investment,
            self.__s.quote_currency,
        )

    # ==========================================================================
    #            C H E C K - P R I C E - R A N G E
    # ==========================================================================

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

        if len(buy_prices := list(self.__s.get_current_buy_prices())) == 0:
            return

        buy_prices.sort(reverse=True)
        for i, price in enumerate(buy_prices[1:]):
            if (
                price == buy_prices[i]
                or (buy_prices[i] / price) - 1 < self.__s.interval / 2
            ):
                for order in self.__s.orderbook.get_orders(filters={"side": "buy"}):
                    if order["price"] == buy_prices[i]:
                        self.handle_cancel_order(txid=order["txid"])
                        break

    def __check_n_open_buy_orders(self: OrderManager) -> None:
        """
        Ensures that there are n open buy orders and will place orders until n.
        """
        LOG.debug(
            "Checking if there are %d open buy orders...",
            self.__s.n_open_buy_orders,
        )
        can_place_buy_order: bool = True
        buy_prices: list[float] = list(self.__s.get_current_buy_prices())

        while (
            (n_active_buy_orders := self.__s.orderbook.count(filters={"side": "buy"}))
            < self.__s.n_open_buy_orders
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
                        if n_active_buy_orders == 0
                        else min(buy_prices)
                    ),
                )

                self.handle_arbitrage(side="buy", order_price=order_price)
                buy_prices = list(self.__s.get_current_buy_prices())
                LOG.info("Length of active buy orders: %s", n_active_buy_orders + 1)
            else:
                LOG.warning("Not enough quote currency available to place buy order!")
                can_place_buy_order = False

    def __check_lowest_cancel_of_more_than_n_buy_orders(self: OrderManager) -> None:
        """
        Cancel the lowest buy order if new higher buy was placed because of an
        executed sell order.
        """
        LOG.debug("Checking if the lowest buy order needs to be canceled...")

        if (
            n_to_cancel := (
                self.__s.orderbook.count(filters={"side": "buy"})
                - self.__s.n_open_buy_orders
            )
        ) > 0:
            for order in self.__s.orderbook.get_orders(
                filters={"side": "buy"},
                order_by=("price", "asc"),
                limit=n_to_cancel,
            ):
                self.handle_cancel_order(txid=order["txid"])

    def __shift_buy_orders_up(self: OrderManager) -> bool:
        """
        Checks if the buy order prices are not to low. If there are too low,
        they get canceled and the ``check_price_range`` function is triggered
        again to place new buy orders.

        Returns ``True`` if the orders get canceled and the
        ``check_price_range`` functions stops.
        """
        LOG.debug("Checking if buy orders need to be shifted up...")

        if (
            max_buy_order := self.__s.orderbook.get_orders(
                filters={"side": "buy"},
                order_by=("price", "desc"),
                limit=1,
            ).first()  # type: ignore[no-untyped-call]
        ) and (
            self.__s.ticker.last
            > max_buy_order["price"]
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
        if self.__s.orderbook.count(filters={"side": "sell"}) == 0:
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

        if self.__s.dry_run:
            LOG.info("Dry run, not placing %s order.", side)
            return

        if side == "buy":
            self.new_buy_order(
                order_price=order_price,
                txid_to_delete=txid_to_delete,
            )
        elif side == "sell":
            self.new_sell_order(
                order_price=order_price,
                txid_to_delete=txid_to_delete,
            )

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
            return

        if txid_to_delete is not None:
            self.__s.orderbook.remove(filters={"txid": txid_to_delete})

        if (
            self.__s.orderbook.count(filters={"side": "buy"})
            >= self.__s.n_open_buy_orders
        ):
            # Don't place new buy orders if there are already enough
            return

        # Check if algorithm reached the max_investment value
        if self.__s.max_investment_reached:
            return

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
        current_balances = self.__s.get_balances()
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
                oflags="post",  # post-only buy orders
            )

            self.__s.pending_txids.add(placed_order["txid"][0])
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
        txid_to_delete: str | None = None,
    ) -> None:
        """Places a new sell order."""
        if self.__s.dry_run:
            LOG.info("Dry run, not placing sell order.")
            return

        if self.__s.strategy == "cDCA":
            LOG.debug("cDCA strategy, not placing sell order.")
            if txid_to_delete is not None:
                self.__s.orderbook.remove(filters={"txid": txid_to_delete})
            return

        LOG.debug("Check conditions for placing a sell order...")

        # ======================================================================
        volume: float | None = None
        if txid_to_delete is not None:  # If corresponding buy order filled
            # GridSell always has txid_to_delete set.

            # Add the txid of the corresponding buy order to the unsold buy
            # order txids in order to ensure that the corresponding sell order
            # will be placed - even if placing now fails.
            if not self.__s.unsold_buy_order_txids.get(
                filters={"txid": txid_to_delete},
            ).first():  # type: ignore[no-untyped-call]
                self.__s.unsold_buy_order_txids.add(
                    txid=txid_to_delete,
                    price=order_price,
                )

            # ==================================================================
            # Get the corresponding buy order in order to retrieve the volume.
            corresponding_buy_order = self.get_orders_info_with_retry(
                txid=txid_to_delete,
            )

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
                    txid_to_delete=txid_to_delete,
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
        fetched_balances = self.__s.get_balances()
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

            if txid_to_delete is not None:
                # Other than with buy orders, we can only delete the
                # corresponding buy order if the sell order was placed.
                self.__s.orderbook.remove(filters={"txid": txid_to_delete})
                self.__s.unsold_buy_order_txids.remove(txid=txid_to_delete)

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
        elif txid_to_delete is not None:
            # TODO: Check if this is appropriate or not
            #       Added logging statement to monitor occurrences
            # ... This would only be the case for GridHODL and SWING, while
            # those should always have enough base currency available... but
            # lets check this for a while.
            LOG.warning(
                "TODO: Not enough funds to place sell order for txid %s",
                txid_to_delete,
            )
            self.__s.orderbook.remove(filters={"txid": txid_to_delete})

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
        order_details = self.get_orders_info_with_retry(txid=txid)

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
            order_details = self.get_orders_info_with_retry(
                txid=txid,
                exit_on_fail=False,
            )
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
                txid_to_delete=txid,
            )

        # ======================================================================
        # Create a buy order for the executed sell order.
        ##
        elif (
            self.__s.orderbook.count(filters={"side": "sell"}, exclude={"txid": txid})
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
                txid_to_delete=txid,
            )
        else:
            # Remove filled order from list of all orders
            self.__s.orderbook.remove(filters={"txid": txid})

    def handle_cancel_order(self: OrderManager, txid: str) -> None:
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
        if self.__s.orderbook.count(filters={"txid": txid}) == 0:
            return

        order_details = self.get_orders_info_with_retry(txid=txid)

        if (
            order_details["descr"]["pair"] != self.__s.altname
            or order_details["userref"] != self.__s.userref
        ):
            return

        if self.__s.dry_run:
            LOG.info("DRY RUN: Not cancelling order: %s", txid)
            return

        LOG.info("Cancelling order: '%s'", txid)

        try:
            self.__s.trade.cancel_order(txid=txid)
        except KrakenUnknownOrderError:
            LOG.info(
                "Order '%s' is already closed. Removing from orderbook...",
                txid,
            )

        self.__s.orderbook.remove(filters={"txid": txid})

        # Check if the order has some vol_exec to sell
        ##
        if float(order_details["vol_exec"]) != 0.0:
            LOG.info(
                "Order '%s' is partly filled - saving those funds.",
                txid,
            )
            b = self.__s.configuration.get()

            # Add vol_exec to remaining funds
            updates = {
                "vol_of_unfilled_remaining": b["vol_of_unfilled_remaining"]
                + float(order_details["vol_exec"]),
            }

            # Set new highest buy price.
            if b["vol_of_unfilled_remaining_max_price"] < float(
                order_details["descr"]["price"],
            ):
                updates |= {
                    "vol_of_unfilled_remaining_max_price": float(
                        order_details["descr"]["price"],
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

    def cancel_all_open_buy_orders(self: OrderManager) -> None:
        """
        Cancels all open buy orders and removes them from the orderbook.
        """
        LOG.info("Cancelling all open buy orders...")
        for txid, order in self.__s.user.get_open_orders(
            userref=self.__s.userref,
        )["open"].items():
            if (
                order["descr"]["type"] == "buy"
                and order["descr"]["pair"] == self.__s.altname
            ):
                self.handle_cancel_order(txid=txid)
                sleep(0.2)  # Avoid rate limiting

        self.__s.orderbook.remove(filters={"side": "buy"})

    def get_orders_info_with_retry(
        self: OrderManager,
        txid: str,
        tries: int = 0,
        max_tries: int = 5,
        exit_on_fail: bool = True,
    ) -> dict | None:
        """
        Returns the order details for a given txid.

        NOTE: We need retry here, since Kraken lacks of fast processing of
              placed/filled orders and making them available via REST API.
        """
        while tries < max_tries and not (
            order_details := self.__s.user.get_orders_info(
                txid=txid,
            ).get(txid)
        ):
            tries += 1
            LOG.warning(
                "Could not find order '%s'. Retry %d/%d in %d seconds...",
                txid,
                tries,
                max_tries,
                (wait_time := 2 * tries),
            )
            sleep(wait_time)

        if exit_on_fail and order_details is None:
            self.__s.save_exit(
                f"Failed to retrieve order info for '{txid}' after"
                f" {max_tries} retries!",
            )
        order_details["txid"] = txid

        return order_details  # type: ignore[no-any-return]
