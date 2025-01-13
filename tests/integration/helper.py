#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#
# pylint: disable=arguments-differ

""" Helper data structures used for integration testing. """

import uuid
from typing import Any, Callable, Self

from kraken.spot import Trade, User


class KrakenAPI(Trade, User):
    """
    Class mocking the User and Trade client of the python-kraken-sdk to
    simulate real trading.

    TODOs:

    - [ ] Properly handle updating the user's current balances. While being at
          it, ensure the integration tests cover cases where the balances are
          not sufficient.
    """

    def __init__(self: Self, **kwargs) -> None:  # noqa: ANN003
        super().__init__(**kwargs)
        self.__orders = {}
        self.__balances = {
            "XXBT": {"balance": "100.0", "hold_trade": "0.0"},
            "ZUSD": {"balance": "1000000.0", "hold_trade": "0.0"},
        }
        self.__fee = 0.0025

    def create_order(self: Self, **kwargs) -> dict:  # noqa: ANN003
        """Create a new order and update balances if needed."""
        txid = str(uuid.uuid4()).upper()
        order = {
            "userref": kwargs["userref"],
            "descr": {
                "pair": "BTCUSD",
                "type": kwargs["side"],
                "ordertype": kwargs["ordertype"],
                "price": kwargs["price"],
            },
            "status": "open",
            "vol": kwargs["volume"],
            "vol_exec": "0.0",
            "cost": "0.0",
            "fee": "0.0",
        }

        if kwargs["side"] == "buy":
            required_balance = float(kwargs["price"]) * float(kwargs["volume"])
            if float(self.__balances["ZUSD"]["balance"]) < required_balance:
                raise ValueError("Insufficient balance to create buy order")
            self.__balances["ZUSD"]["balance"] = str(
                float(self.__balances["ZUSD"]["balance"]) - required_balance,
            )
            self.__balances["ZUSD"]["hold_trade"] = str(
                float(self.__balances["ZUSD"]["hold_trade"]) + required_balance,
            )
        elif kwargs["side"] == "sell":
            if float(self.__balances["XXBT"]["balance"]) < float(kwargs["volume"]):
                raise ValueError("Insufficient balance to create sell order")
            self.__balances["XXBT"]["balance"] = str(
                float(self.__balances["XXBT"]["balance"]) - float(kwargs["volume"]),
            )
            self.__balances["XXBT"]["hold_trade"] = str(
                float(self.__balances["XXBT"]["hold_trade"]) + float(kwargs["volume"]),
            )

        self.__orders[txid] = order
        return {"txid": [txid]}

    def fill_order(self: Self, txid: str, volume: float | None = None) -> None:
        """Fill an order and update balances."""
        order = self.__orders.get(txid, {})
        if not order:
            return

        if volume is None:
            volume = float(order["vol"])

        if volume > float(order["vol"]) - float(order["vol_exec"]):
            raise ValueError(
                "Cannot fill order with volume higher than remaining order volume",
            )

        executed_volume = float(order["vol_exec"]) + volume
        remaining_volume = float(order["vol"]) - executed_volume

        order["fee"] = str(float(order["vol_exec"]) * self.__fee)
        order["vol_exec"] = str(executed_volume)
        order["cost"] = str(
            executed_volume * float(order["descr"]["price"]) + float(order["fee"]),
        )

        if remaining_volume <= 0:
            order["status"] = "closed"
        else:
            order["status"] = "open"

        self.__orders[txid] = order

        if order["descr"]["type"] == "buy":
            self.__balances["XXBT"]["balance"] = str(
                float(self.__balances["XXBT"]["balance"]) + volume,
            )
            self.__balances["ZUSD"]["balance"] = str(
                float(self.__balances["ZUSD"]["balance"]) - float(order["cost"]),
            )
            self.__balances["ZUSD"]["hold_trade"] = str(
                float(self.__balances["ZUSD"]["hold_trade"]) - float(order["cost"]),
            )
        elif order["descr"]["type"] == "sell":
            self.__balances["XXBT"]["balance"] = str(
                float(self.__balances["XXBT"]["balance"]) - volume,
            )
            self.__balances["XXBT"]["hold_trade"] = str(
                float(self.__balances["XXBT"]["hold_trade"]) - volume,
            )
            self.__balances["ZUSD"]["balance"] = str(
                float(self.__balances["ZUSD"]["balance"]) + float(order["cost"]),
            )

    async def on_ticker_update(self: Self, callback: Callable, last: float) -> None:
        """Update the ticker and fill orders if needed."""
        await callback(
            {
                "channel": "ticker",
                "data": [{"symbol": "BTC/USD", "last": last}],
            },
        )

        async def fill_order(txid: str) -> None:
            self.fill_order(txid)
            await callback(
                {
                    "channel": "executions",
                    "type": "update",
                    "data": [{"exec_type": "filled", "order_id": txid}],
                },
            )

        for order in self.get_open_orders()["open"].values():
            if (
                order["descr"]["type"] == "buy"
                and float(order["descr"]["price"]) >= last
            ) or (
                order["descr"]["type"] == "sell"
                and float(order["descr"]["price"]) <= last
            ):
                await fill_order(order["txid"])

    def cancel_order(self: Self, txid: str) -> None:
        """Cancel an order and update balances if needed."""
        order = self.__orders.get(txid, {})
        if not order:
            return

        order.update({"status": "canceled"})
        self.__orders[txid] = order

        if order["descr"]["type"] == "buy":
            executed_cost = float(order["vol_exec"]) * float(order["descr"]["price"])
            remaining_cost = (
                float(order["vol"]) * float(order["descr"]["price"]) - executed_cost
            )
            self.__balances["ZUSD"]["balance"] = str(
                float(self.__balances["ZUSD"]["balance"]) + remaining_cost,
            )
            self.__balances["ZUSD"]["hold_trade"] = str(
                float(self.__balances["ZUSD"]["hold_trade"]) - remaining_cost,
            )
            self.__balances["XXBT"]["balance"] = str(
                float(self.__balances["XXBT"]["balance"]) - float(order["vol_exec"]),
            )
        elif order["descr"]["type"] == "sell":
            remaining_volume = float(order["vol"]) - float(order["vol_exec"])
            self.__balances["XXBT"]["balance"] = str(
                float(self.__balances["XXBT"]["balance"]) + remaining_volume,
            )
            self.__balances["XXBT"]["hold_trade"] = str(
                float(self.__balances["XXBT"]["hold_trade"]) - remaining_volume,
            )
            self.__balances["ZUSD"]["balance"] = str(
                float(self.__balances["ZUSD"]["balance"]) - float(order["cost"]),
            )

    def cancel_all_orders(self: Self, **kwargs: Any) -> None:  # noqa: ARG002
        """Cancel all open orders."""
        for txid in self.__orders:
            self.cancel_order(txid)

    def get_open_orders(self, **kwargs: Any) -> dict:  # noqa: ARG002
        """Get all open orders."""
        return {
            "open": {k: v for k, v in self.__orders.items() if v["status"] == "open"},
        }

    def get_orders_info(self: Self, txid: str) -> dict:
        """Get information about a specific order."""
        if (order := self.__orders.get(txid, None)) is not None:
            return {txid: order}
        return {}

    def get_balances(self: Self, **kwargs: Any) -> dict:  # noqa: ARG002
        """Get the user's current balances."""
        return self.__balances
