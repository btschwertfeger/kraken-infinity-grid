#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Module that implements the setup functions of the trading algorithm."""

from __future__ import annotations

import traceback
from logging import getLogger
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from kraken_infinity_grid.gridbot import KrakenInfinityGridBot

LOG = getLogger(__name__)


class SetupManager:
    """SetupManager class to manage the setup of the trading algorithm."""

    def __init__(self: SetupManager, strategy: KrakenInfinityGridBot) -> None:
        LOG.debug("Initializing SetupManager...")
        self.__s = strategy

    def __update_orderbook_get_open_orders(self: SetupManager) -> tuple[list, list]:
        """Get the open orders and txid as lists."""
        LOG.info("  - Retrieving open orders from upstream...")

        open_orders, open_txids = [], []
        for txid, order in self.__s.user.get_open_orders(
            userref=self.__s.userref,
        )["open"].items():
            if order["descr"]["pair"] == self.__s.altname:
                order["txid"] = txid  # IMPORTANT
                open_orders.append(order)
                open_txids.append(order["txid"])
        return open_orders, open_txids

    def __update_order_book_handle_closed_order(
        self: SetupManager,
        closed_order: dict,
    ) -> None:
        """
        Gets executed when an order of the local orderbook was closed in the
        upstream orderbook during the ``update_orderbook`` function in the init
        of the algorithm.

        This function triggers the Telegram message of the executed order and
        places a new order.
        """
        LOG.info("Handling executed order: %s", closed_order["txid"])
        closed_order["side"] = closed_order["descr"]["type"]

        message = str(
            f"✅ {self.__s.symbol}: {closed_order['side'][0].upper()}{closed_order['side'][1:]} "
            "order executed"
            f"\n ├ Price » {closed_order['price']} {self.__s.quote_currency}"
            f"\n ├ Size » {closed_order['vol_exec']} {self.__s.base_currency}"
            f"\n └ Size in {self.__s.quote_currency} » "
            f"{float(closed_order['price']) * float(closed_order['vol_exec'])}",
        )

        self.__s.t.send_to_telegram(message)

        # ======================================================================
        # If a buy order was filled, the sell order needs to be placed.
        if closed_order["side"] == "buy":
            self.__s.om.handle_arbitrage(
                side="sell",
                order_price=self.__s.get_order_price(
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
                self.__s.orderbook.count(
                    filters={"side": "sell"},
                    exclude={"txid": closed_order["txid"]},
                )
                != 0
            ):
                self.__s.om.handle_arbitrage(
                    side="buy",
                    order_price=self.__s.get_order_price(
                        side="buy",
                        last_price=float(closed_order["price"]),
                    ),
                    txid_to_delete=closed_order["txid"],
                )
            else:
                self.__s.orderbook.remove(filters={"txid": closed_order["txid"]})

    def __update_order_book(self: SetupManager) -> None:
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
        open_orders, open_txids = self.__update_orderbook_get_open_orders()

        # ======================================================================
        # Orders of the upstream which are not yet tracked in the local
        # orderbook will now be added to the local orderbook.
        ##
        local_txids = [order["txid"] for order in self.__s.orderbook.get_orders()]
        something_changed = False
        for order in open_orders:
            if order["txid"] not in local_txids:
                LOG.info(
                    "  - Adding upstream order to local orderbook: %s",
                    order["txid"],
                )
                self.__s.orderbook.add(order)
                something_changed = True
        if not something_changed:
            LOG.info("  - Nothing changed!")

        # ======================================================================
        # Check all orders of the local orderbook against those from upstream.
        # If they got filled -> place new orders.
        # If canceled -> remove from local orderbook.
        ##
        for order in self.__s.orderbook.get_orders():
            if order["txid"] not in open_txids:
                closed_order = self.__s.om.get_orders_info_with_retry(
                    txid=order["txid"],
                )
                # ==============================================================
                # Order was filled
                if closed_order["status"] == "closed":
                    self.__update_order_book_handle_closed_order(
                        closed_order=closed_order,
                    )

                # ==============================================================
                # Order was closed
                elif closed_order["status"] in {"canceled", "expired"}:
                    self.__s.orderbook.remove(filters={"txid": order["txid"]})

                else:
                    # pending || open order - still active
                    ##
                    continue

        # There are no more filled/closed and cancelled orders in the local
        # orderbook and all upstream orders are tracked locally.
        LOG.info("- Orderbook initialized!")

    def __check_asset_pair_parameter(self: Self) -> None:
        """Check the asset pair parameter."""
        LOG.info("- Checking asset pair parameters...")
        pair_data = self.__s.market.get_asset_pairs(
            pair=[self.__s.symbol.replace("/", "")],
        )
        LOG.debug(pair_data)

        self.__s.xsymbol = next(iter(pair_data.keys()))
        data = pair_data[self.__s.xsymbol]

        self.__s.altname = data["altname"]
        self.__s.zbase_currency = data["base"]  # XXBT
        self.__s.xquote_currency = data["quote"]  # ZEUR
        self.__s.cost_decimals = data["cost_decimals"]  # 5, i.e., 0.00001 EUR

        if self.__s.fee is None:
            # This is the case if the '--fee' parameter was not passed, then we
            # take the highest maker fee.
            self.__s.fee = float(data["fees_maker"][0][1]) / 100

        self.__s.amount_per_grid_plus_fee = self.__s.amount_per_grid * (
            1 + self.__s.fee
        )

    def __check_configuration_changes(self: Self) -> None:
        """
        Checking if the database content match with the setup parameters.

        Checking if the order size or the interval have changed, requiring
        all open buy orders to be cancelled.
        """
        LOG.info("- Checking configuration changes...")
        cancel_all_orders = False

        if self.__s.amount_per_grid != self.__s.configuration.get()["amount_per_grid"]:
            LOG.info(" - Amount per grid changed => cancel open buy orders soon...")
            self.__s.configuration.update({"amount_per_grid": self.__s.amount_per_grid})
            cancel_all_orders = True

        if self.__s.interval != self.__s.configuration.get()["interval"]:
            LOG.info(" - Interval changed => cancel open buy orders soon...")
            self.__s.configuration.update({"interval": self.__s.interval})
            cancel_all_orders = True

        if cancel_all_orders:
            self.__s.om.cancel_all_open_buy_orders()

        LOG.info("- Configuration checked and up-to-date!")

    def prepare_for_trading(self: Self) -> None:
        """
        This function gets triggered once during the setup of the algorithm. It
        prepares the algorithm for live trading by checking the asset pair
        parameters, syncing the local with the upstream orderbook, place missing
        sell orders that not get through because of e.g. "missing funds", and
        updating the orderbook.
        """
        LOG.info(
            "Preparing for trading by initializing and updating local orderbook...",
        )

        self.__s.t.send_to_telegram(
            message=f"✅ {self.__s.name} - {self.__s.symbol} is live again!",
            exception=True,
            log=False,
        )
        # ======================================================================

        # Check the fee and altname of the asset pair
        ##
        self.__check_asset_pair_parameter()

        # Append orders to local orderbook in case they are not saved yet
        ##
        self.__s.om.assign_all_pending_transactions()

        # Try to place missing sell orders that not get through because
        # of "missing funds".
        ##
        self.__s.om.add_missed_sell_orders()

        # Update the orderbook, check for closed, filled, cancelled trades,
        # and submit new orders if necessary.
        ##

        try:
            self.__update_order_book()
        except Exception as e:  # noqa: BLE001
            message = f"Exception in update_orderbook: {e}: {traceback.format_exc()}"
            self.__s.save_exit(message)

        # Check if the configured amount per grid or the interval have changed,
        # requiring a cancellation of all open buy orders.
        ##
        self.__check_configuration_changes()

        # Everything is done, the bot is ready to trade live.
        ##
        self.__s.is_ready_to_trade = True
        LOG.info("Algorithm is ready to trade!")

        # Checks if the open orders match the range and cancel if
        # necessary. It is the heart of this algorithm and gets
        # triggered every time the price changes.
        ##
        self.__s.om.check_price_range()
        self.__s.init_done = True
