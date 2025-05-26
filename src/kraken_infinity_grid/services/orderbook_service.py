# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from logging import getLogger



from typing import Self, Iterable
from kraken_infinity_grid.core.event_bus import EventBus
from time import sleep
from decimal import Decimal
from kraken_infinity_grid.exceptions import GridBotStateError
from kraken_infinity_grid.core.state_machine import States, StateMachine
from kraken_infinity_grid.infrastructure.database import (
    Orderbook,
    PendingTxids,
    UnsoldBuyOrderTxids,
)

LOG = getLogger(__name__)


class OrderbookService:
    """Service for managing the orderbook."""

    def __init__(
        self,
        rest_api,
        event_bus: EventBus,
        state_machine: StateMachine,
        orderbook: Orderbook,
        pending_txids: PendingTxids,
        unsold_buy_order_txids: UnsoldBuyOrderTxids,
    ) -> None:
        self._rest_api = rest_api
        self._event_bus = event_bus
        self._state_machine = state_machine
        self._orderbook = orderbook
        self._pending_txids = pending_txids
        self._unsold_buy_order_txids = unsold_buy_order_txids

    def add_missed_sell_orders(self: Self) -> None:
        """
        This functions can create sell orders in case there is at least one
        executed buy order that is missing its sell order.

        Missed sell orders came into place when a buy was executed and placing
        the sell failed. An entry to the missed sell order id table is added
        right before placing a sell order.
        """
        LOG.info("- Create sell orders based on unsold buy orders...")
        for entry in self._unsold_buy_order_txids.get():
            LOG.info("  - %s", entry)
            self.handle_arbitrage(
                side="sell",
                order_price=entry["price"],
                txid_to_delete=entry["txid"],
            )

    def assign_all_pending_transactions(self: Self) -> None:
        """Assign all pending transactions to the orderbook."""
        LOG.info("- Checking pending transactions...")
        for order in self._pending_txids.get():
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
        LOG.info("Processing order '%s' ...", txid)
        order_details = self.get_orders_info_with_retry(txid=txid)
        LOG.debug("- Order information: %s", order_details)

        if (
            order_details["descr"]["pair"] != self.__s.altname
            or order_details["userref"] != self.__s.userref
        ):
            LOG.info("Order '%s' does not belong to this instance.", txid)
            return

        if self._pending_txids.count(filters={"txid": order_details["txid"]}) != 0:
            self._orderbook.add(order_details)
            self._pending_txids.remove(order_details["txid"])
        else:
            self._orderbook.update(
                order_details,
                filters={"txid": order_details["txid"]},
            )
            LOG.info("Updated order '%s' in orderbook.", order_details["txid"])

        LOG.info(
            "Current investment: %f / %d %s",
            self.__s.investment,
            self.__s.max_investment,
            self.__s.quote_currency,
        )

    def get_current_buy_prices(self: Self) -> Iterable[float]:
        """Returns a generator of the prices of open buy orders."""
        LOG.debug("Getting current buy prices...")
        for order in self._orderbook.get_orders(filters={"side": "buy"}):
            yield order["price"]

    def get_value_of_orders(self: Self, orders: Iterable) -> float:
        """Returns the overall invested quote that is invested"""
        LOG.debug("Getting value of open orders...")
        investment = sum(
            float(order["price"]) * float(order["volume"]) for order in orders
        )
        LOG.debug("Value of open orders: %d %s", investment, self.quote_currency)
        return investment

    @property
    def investment(self: Self) -> float:
        """Returns the current investment based on open orders."""
        return self.get_value_of_orders(orders=self._orderbook.get_orders())

    @property
    def max_investment_reached(self: Self) -> bool:
        """Returns True if the maximum investment is reached."""
        return (
            self.max_investment <= self.investment + self.amount_per_grid_plus_fee
        ) or (self.max_investment <= self.investment)

    def get_balances(self: Self) -> dict[str, float]:
        """
        Returns the available and overall balances of the quote and base
        currency.
        """
        LOG.debug("Retrieving the user's balances...")

        base_balance = Decimal(0)
        base_available = Decimal(0)
        quote_balance = Decimal(0)
        quote_available = Decimal(0)

        for symbol, data in self._rest_api.get_balances().items():
            if symbol == self.zbase_currency:
                base_balance = Decimal(data["balance"])
                base_available = base_balance - Decimal(data["hold_trade"])
            elif symbol == self.xquote_currency:
                quote_balance = Decimal(data["balance"])
                quote_available = quote_balance - Decimal(data["hold_trade"])

        balances = {
            "base_balance": float(base_balance),
            "quote_balance": float(quote_balance),
            "base_available": float(base_available),
            "quote_available": float(quote_available),
        }
        LOG.debug("Retrieved balances: %s", balances)
        return balances

    # ==========================================================================
    #            C H E C K - P R I C E - R A N G E
    # ==========================================================================

    def __check_pending_txids(self: Self) -> bool:
        """
        Skip checking the price range, because first all missing orders
        must be assigned. Otherwise this could lead to double trades.

        Returns False if okay and True if ``check_price_range`` must be skipped.
        """
        if self._pending_txids.count() != 0:
            LOG.info("check_price_range... skip because pending_txids != 0")
            self.assign_all_pending_transactions()
            return True
        return False

    # ==========================================================================
    #           C R E A T E / C A N C E L - O R D E R S
    # ==========================================================================
    def cancel_all_open_buy_orders(self: Self) -> None:
        """
        Cancels all open buy orders and removes them from the orderbook.
        """
        LOG.info("Cancelling all open buy orders...")
        for txid, order in self._rest_api.get_open_orders(
            userref=self.__s.userref,
        )["open"].items():
            if (
                order["descr"]["type"] == "buy"
                and order["descr"]["pair"] == self.__s.altname
            ):
                self.handle_cancel_order(txid=txid)
                sleep(0.2)  # Avoid rate limiting

        self._orderbook.remove(filters={"side": "buy"})

    def get_orders_info_with_retry(
        self: Self,
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
            order_details := self._rest_api.get_orders_info(
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
            LOG.error(
                "Failed to retrieve order info for '%s' after %d retries!",
                txid,
                max_tries,
            )
            self._state_machine.transition_to(States.ERROR)
            raise GridBotStateError(
                f"Failed to retrieve order info for '{txid}' after {max_tries} retries!",
            )

        order_details["txid"] = txid
        return order_details  # type: ignore[no-any-return]
