#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#
# pylint: disable=arguments-differ

""" Helper data structures used for integration testing. """

import uuid
from typing import Self

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

    def create_order(self: Self, **kwargs) -> None:  # noqa: ANN003
        self.__orders |= {
            (txid := str(uuid.uuid4()).upper()): {
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
            },
        }

        return {"txid": [txid]}

    def cancel_order(self: Self, txid: str) -> None:
        self.__orders.get(txid, {}).update({"status": "canceled"})

    def fill_order(self: Self, txid: str) -> None:
        order = self.__orders.get(txid, {})
        order["fee"] = str(float(order["vol"]) * 0.0025)
        order |= {
            "status": "closed",
            "vol_exec": order["vol"],
            "cost": str(float(order["vol"]) + float(order["fee"])),
        }

    def cancel_all_orders(self, **kwargs) -> None:  # noqa: ARG002,ANN003
        for txid in self.__orders:
            self.cancel_order(txid)

    def get_open_orders(self, **kwargs) -> dict:  # noqa: ARG002,ANN003
        return {
            "open": {k: v for k, v in self.__orders.items() if v["status"] == "open"},
        }

    def get_orders_info(self: Self, txid: str) -> dict:
        if (order := self.__orders.get(txid, None)) is not None:
            return {txid: order}
        return {}

    def get_balances(self, **kwargs) -> dict:  # noqa: ARG002, ANN003
        return self.__balances
