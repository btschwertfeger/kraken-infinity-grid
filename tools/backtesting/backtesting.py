# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#
# pylint: disable=arguments-differ

"""
Backtesting script for the Kraken Infinity Grid Bot.

The backtesting.py script can be used to backtest different strategies and their
configuration against custom price movements. It is intended to be used as
orientation and guidance in order to estimate profitability and the optimal
configuration in different market situations.

Except from the configuration, an iterable including float values for prices are
the only inputs for running the backtest.

This script is far from optimal, but it should give a good overview of the
functionality of the Kraken Infinity Grid Bot. It is not intended to be used for
real trading or making any final financial decisions.

It does not respect the following situations for simplicity:

- Partly filled buy orders
- External cancellation of orders
- Interruptions
- Failed orders (of any kind)
- Telegram messaging
- Real trading

Example:

The following example demonstrates how to run this script and the expected
output if the full history of XBTEUR was downloaded from Kraken (see main
function).

.. code-block:: bash

    python3 backtesting.py
    100%|█████████████████████████████████| 100000/100000 [01:24<00:00, 1185.80it/s]
    ********************************************************************************
    Strategy: GridHODL
    Final price: 633.1639
    Executed buy orders: 472
    Executed sell orders: 467
    Final balances:
    BTC: {'balance': 3.202440239999995, 'hold_trade': 0.6135451499999994}
    EUR: {'balance': 489.92317716484786, 'hold_trade': 453.53667409747777}
    Market price: 2517.5927290401805 EUR
    ********************************************************************************

"""

import asyncio
import logging
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Generator, Iterable, Self
from unittest.mock import patch

from kraken.spot import Market, Trade, User
from tqdm import tqdm

from kraken_infinity_grid.gridbot import KrakenInfinityGridBot


@contextmanager
def no_sleep() -> Generator:
    """Context manager to disable all sleep calls during backtesting"""
    with (
        patch("time.sleep", return_value=None),
        patch("asyncio.sleep", return_value=None),
        patch("kraken_infinity_grid.gridbot.sleep", return_value=None),
        patch("kraken_infinity_grid.order_management.sleep", return_value=None),
    ):
        yield


class KrakenAPIMock(Trade, User, Market):
    """
    Class mocking the User, Market and Trade client of the python-kraken-sdk to
    simulate real trading.
    """

    def __init__(self: Self, kraken_config: dict, callback: Callable) -> None:
        """
        Initialize the KrakenAPIMock with the given configuration and callback.

        Args:
            kraken_config (dict): Configuration for the Kraken API mock.
            callback (Callable): Callback function to handle ticker updates.
        """
        super().__init__()  # We don't want to pass secrets here!
        self.__callback = callback

        self.__orders = {}
        self.__balances = kraken_config["balances"]
        self.__fee = kraken_config.get("fee")

        asset_pair_parameter = Market().get_asset_pairs(
            pair=kraken_config["base_currency"] + kraken_config["quote_currency"],
        )
        self.__xsymbol = next(iter(asset_pair_parameter.keys()))
        asset_pair_parameter = asset_pair_parameter[self.__xsymbol]
        self.__altname = asset_pair_parameter["altname"]
        self.base = asset_pair_parameter["base"]
        self.quote = asset_pair_parameter["quote"]
        self.__symbol = (
            f"{kraken_config['base_currency']}/{kraken_config['quote_currency']}"
        )

        if not self.__fee:
            self.__fee = asset_pair_parameter["fees_maker"][0][1]

        self.n_exec_sell_orders = 0
        self.n_exec_buy_orders = 0

    def create_order(self: Self, **kwargs: Any) -> dict:
        """
        Create a new order and update balances if needed.

        Args:
            kwargs: Order parameters including userref, side, ordertype, price,
                    and volume.

        Returns:
            dict: Transaction ID of the created order.
        """
        txid = str(uuid.uuid4()).upper()
        order = {
            "userref": kwargs["userref"],
            "descr": {
                "pair": self.__altname,
                "type": kwargs["side"],
                "ordertype": kwargs["ordertype"],
                "price": kwargs["price"],
            },
            "status": "open",
            "vol": kwargs["volume"],
            "vol_exec": "0.0",
            "cost": "0.0",
            "fee": str(float(kwargs["price"]) * float(kwargs["volume"]) * self.__fee),
        }
        if order["descr"]["type"] == "buy":
            required_balance = float(order["descr"]["price"]) * float(
                order["vol"],
            ) + float(order["fee"])

            if float(self.__balances[self.quote]["balance"]) < required_balance:
                raise ValueError("Insufficient balance to create buy order")

            self.__balances[self.quote]["hold_trade"] = str(
                float(self.__balances[self.quote]["hold_trade"]) + required_balance,
            )

        elif order["descr"]["type"] == "sell":
            if float(self.__balances[self.base]["balance"]) < float(order["vol"]):
                raise ValueError("Insufficient balance to create sell order")

            self.__balances[self.base]["hold_trade"] = str(
                float(self.__balances[self.base]["hold_trade"]) + float(order["vol"]),
            )

            # Hold trade fee
            self.__balances[self.quote]["hold_trade"] = str(
                float(self.__balances[self.quote]["hold_trade"]) + float(order["fee"]),
            )

        self.__orders[txid] = order
        return {"txid": [txid]}

    def fill_order(self: Self, txid: str) -> None:
        """
        Fill an order and update balances.

        Args:
            txid (str): Transaction ID of the order to be filled.
        """
        if not (order := self.__orders.get(txid)):
            return

        self.__orders[txid] |= {
            "status": "closed",
            "vol_exec": order["vol"],
            "cost": str(
                float(order["vol"]) * float(order["descr"]["price"])
                + float(order["fee"]),
            ),
        }

        if order["descr"]["type"] == "buy":
            self.n_exec_buy_orders += 1

            self.__balances[self.base]["balance"] = str(
                float(self.__balances[self.base]["balance"])
                + float(self.__orders[txid]["vol_exec"]),
            )

            self.__balances[self.quote]["balance"] = str(
                float(self.__balances[self.quote]["balance"])
                - float(self.__orders[txid]["cost"]),
            )

            self.__balances[self.quote]["hold_trade"] = str(
                float(self.__balances[self.quote]["hold_trade"])
                - float(self.__orders[txid]["cost"]),
            )
        elif order["descr"]["type"] == "sell":
            self.n_exec_sell_orders += 1

            self.__balances[self.quote]["balance"] = str(
                float(self.__balances[self.quote]["balance"])
                + float(self.__orders[txid]["vol_exec"])
                * float(self.__orders[txid]["descr"]["price"])
                - float(self.__orders[txid]["fee"]),
            )

            self.__balances[self.base]["balance"] = str(
                float(self.__balances[self.base]["balance"])
                - float(self.__orders[txid]["vol_exec"]),
            )
            self.__balances[self.base]["hold_trade"] = str(
                float(self.__balances[self.base]["hold_trade"])
                - float(self.__orders[txid]["vol_exec"]),
            )

    async def on_ticker_update(self: Self, last: float) -> None:
        """
        Update the ticker and fill orders if needed.

        Args:
            last (float): The latest price.
        """
        await self.__callback(
            {
                "channel": "ticker",
                "data": [{"symbol": self.__symbol, "last": last}],
            },
        )

        async def fill_order(txid: str) -> None:
            self.fill_order(txid)
            await self.__callback(
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
        """
        Cancel an order and update balances if needed.

        Args:
            txid (str): Transaction ID of the order to be canceled.
        """
        order = self.__orders.get(txid, {})
        if not order:
            return

        order.update({"status": "canceled"})
        self.__orders[txid] = order

        if order["descr"]["type"] == "buy":
            self.__balances[self.quote]["hold_trade"] = str(
                float(self.__balances[self.quote]["hold_trade"])
                - float(order["vol"]) * float(order["descr"]["price"]),
            )
        elif order["descr"]["type"] == "sell":
            self.__balances[self.base]["hold_trade"] = str(
                float(self.__balances[self.base]["hold_trade"]) - float(order["vol"]),
            )

    def cancel_all_orders(self: Self, **kwargs: Any) -> None:  # noqa: ARG002
        """
        Cancel all open orders.
        """
        for txid in self.__orders:
            self.cancel_order(txid)

    def get_open_orders(self, **kwargs: Any) -> dict:  # noqa: ARG002
        """
        Get all open orders.

        Returns:
            dict: Dictionary of open orders.
        """
        return {
            "open": {k: v for k, v in self.__orders.items() if v["status"] == "open"},
        }

    def get_orders_info(self: Self, txid: str) -> dict:
        """
        Get information about a specific order.

        Args:
            txid (str): Transaction ID of the order.

        Returns:
            dict: Dictionary containing order information.
        """
        if (order := self.__orders.get(txid, None)) is not None:
            return {txid: order}
        return {}

    def get_balances(self: Self, **kwargs: Any) -> dict:  # noqa: ARG002
        """
        Get the user's current balances.

        Returns:
            dict: Dictionary containing the user's balances.
        """
        return {
            self.base: {
                "balance": float(self.__balances[self.base]["balance"]),
                "hold_trade": float(self.__balances[self.base]["hold_trade"]),
            },
            self.quote: {
                "balance": float(self.__balances[self.quote]["balance"]),
                "hold_trade": float(self.__balances[self.quote]["hold_trade"]),
            },
        }


class Backtest:
    """
    Class to perform backtesting of the Kraken Infinity Grid Bot.
    """

    def __init__(
        self: Self,
        strategy_config: dict,
        db_config: dict,
        balances: dict,
    ) -> None:
        """
        Initialize the Backtest with the given strategy configuration, database
        configuration, and balances.

        Args:
            strategy_config (dict): Configuration for the trading strategy.
            db_config (dict): Configuration for the database. balances (dict):
            Initial balances for the backtest.
        """
        strategy_config |= {
            # Ignore Telegram stuff
            "telegram_token": "",
            "telegram_chat_id": "",
            "exception_token": "",
            "exception_chat_id": "",
        }

        self.instance = KrakenInfinityGridBot(
            key="key",
            secret="secret",  # noqa: S106
            config=strategy_config,
            db_config=db_config,
        )

        # We don't need to test for telegram messages here...
        self.instance.t.send_to_telegram = lambda message, exception=False, log=True: (
            logging.getLogger().info(message)
            if log and not exception
            else logging.getLogger().error(message) if exception and log else None
        )

        balances["quote_currency"] = strategy_config["quote_currency"]
        balances["base_currency"] = strategy_config["base_currency"]
        if "fee" in strategy_config:
            balances["fee"] = strategy_config["fee"]

        self.api = KrakenAPIMock(
            kraken_config=balances,
            callback=self.instance.on_message,
        )
        self.instance.user = self.api
        self.instance.market = self.api
        self.instance.trade = self.api

    async def run(self: Self, prices: Iterable) -> None:
        """
        Run the configured strategy against a series of prices.

        Args:
            prices (Iterable): Iterable of float values representing price
                               movements.
        """
        with no_sleep():
            # Initialization
            await self.instance.on_message(
                {
                    "channel": "executions",
                    "type": "snapshot",
                    "data": [{"exec_type": "canceled", "order_id": "txid0"}],
                },
            )
            # Run against prices
            if logging.getLogger(__name__).getEffectiveLevel() < logging.ERROR:
                for price in prices:
                    await self.api.on_ticker_update(price)
            else:
                for price in tqdm(prices):
                    await self.api.on_ticker_update(price)

    def summary(self: Self) -> None:
        """
        Print the summary of the backtest.
        """
        print("*" * 80)
        print(f"Strategy: {self.instance.strategy}")
        print(f"Final price: {self.instance.ticker.last}")
        print(f"Executed buy orders: {self.api.n_exec_buy_orders}")
        print(f"Executed sell orders: {self.api.n_exec_sell_orders}")
        print("Final balances:")

        balances = self.api.get_balances()
        print(f"{self.instance.base_currency}: {balances[self.api.base]}")
        print(f"{self.instance.quote_currency}: {balances[self.api.quote]}")
        market_price = (
            balances[self.api.base]["balance"] * self.instance.ticker.last
            + balances[self.api.quote]["balance"]
        )
        print(
            f"Market price: {market_price} {self.instance.quote_currency}",
        )
        print("*" * 80)


async def main() -> None:
    """
    Main function to run the backtest.
    """
    bt = Backtest(
        strategy_config={
            "strategy": "GridHODL",
            "userref": 1,
            "name": "Backtester",
            "interval": 0.02,
            "amount_per_grid": 100,
            "max_investment": 1000,
            "n_open_buy_orders": 5,
            "base_currency": "BTC",
            "quote_currency": "EUR",
            "fee": 0.0026,
        },
        db_config={"sqlite_file": ":memory:"},
        balances={
            "balances": {
                "XXBT": {"balance": "0.0", "hold_trade": "0.0"},
                "ZEUR": {"balance": "1000.0", "hold_trade": "0.0"},
            },
        },
    )

    try:
        # If you downloaded the historical data from Kraken, you can backtest the
        # kraken-infinity-grid as follows:
        # import pandas as pd
        # for chunk in pd.read_csv("XBTEUR.csv", chunksize=10**5):
        #     prices = chunk.iloc[:, 1].astype(float)
        #     await bt.run(prices)
        #     break # Remove the break to get through the full data set ....

        # Otherwise just use dummy data:
        await bt.run(
            prices=(
                50000.0,
                49000.0,
                48000.0,
                47000.0,
                46000.0,
                45000.0,
                46000.0,
                47000.0,
                48000.0,
                49000.0,
                50000.0,
                49000.0,
                48000.0,
                47000.0,
                46000.0,
                45000.0,
                46000.0,
                47000.0,
                48000.0,
                49000.0,
                50000.0,
                49000.0,
                48000.0,
                47000.0,
                46000.0,
                45000.0,
                46000.0,
                47000.0,
                48000.0,
                49000.0,
                50000.0,
                60000.0,
            ),
        )
    finally:
        await bt.instance.close()
        bt.summary()


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)8s | %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
        level=logging.ERROR,
    )
    asyncio.run(main())
