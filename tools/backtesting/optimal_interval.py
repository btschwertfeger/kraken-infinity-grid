#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

"""
This script performs backtesting to find the optimal interval for a grid trading
strategy using historical OHLC data from the Kraken API. The script iterates
through different intervals and evaluates the performance of the strategy to
determine the best interval.

This script provides a rough estimation of the optimal interval based on hourly
data of the last 30 days. One should keep in mind, that the price does move way
more than only in hourly intervals!

Example:

(The output depends on the adjustments made in this script)

>>> python3 -m venv venv
>>> source venv/bin/activate
>>> pip install --compile asyncio python-kraken-sdk pandas prettytable
>>> python3 optimal_interval.py

Results (sorted by Market Price):
+----------------+--------------------+---------+--------+--------------------+---------------------+-----------------------+-----------------------+-------------------+-------------------+
|    Interval    | Market Price (EUR) | N Sells | N Buys | Trade volume (EUR) | Volume-based profit |      BTC (total)      |    BTC (hold trade)   |    EUR (total)    |  EUR (hold trade) |
+----------------+--------------------+---------+--------+--------------------+---------------------+-----------------------+-----------------------+-------------------+-------------------+
| 0.0190 (1.90%) |     1004.1240      |    20   |   25   |        1125        |       0.3666%       |       0.00135394      | 0.0012649999999999996 | 876.3865342775174 | 77.12760838855303 |
| 0.0330 (3.30%) |     1003.4326      |    8    |   10   |        450         |       0.7628%       | 0.0005604900000000001 | 0.0004896200000000001 | 950.5531847476507 |  75.999660600192  |
| 0.0160 (1.60%) |     1003.2277      |    27   |   34   |        1525        |       0.2116%       | 0.0018693099999999995 | 0.0017740500000000003 | 826.8676028395107 |  77.652266790541  |
| 0.0180 (1.80%) |     1003.1033      |    19   |   24   |        1075        |       0.2887%       | 0.0013439300000000001 | 0.0012647499999999998 | 876.3101997599524 | 77.02656068363102 |
| 0.0340 (3.40%) |     1002.9237      |    7    |   9    |        400         |       0.7309%       | 0.0005558799999999999 | 0.0004896200000000001 | 950.4791527176708 |   75.89962503618  |
.............................................................................................................................................................................................
.............................................................................................................................................................................................
.............................................................................................................................................................................................
| 0.0380 (3.80%) |      999.7021      |    2    |   5    |        175         |       -0.1702%      |       0.00079097      | 0.0007496299999999999 |  925.078047041516 | 75.57393903927805 |
| 0.0360 (3.60%) |      999.6662      |    3    |   6    |        225         |       -0.1484%      | 0.0007897900000000001 | 0.0007437099999999999 |  925.153431611764 | 75.67446459388103 |
| 0.0120 (1.20%) |      999.5220      |    41   |   50   |        2275        |       -0.0210%      | 0.0023493300000000006 |       0.0022603       | 777.8744561532236 | 78.87877406765506 |
+----------------+--------------------+---------+--------+--------------------+---------------------+-----------------------+-----------------------+-------------------+-------------------+
"""

import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import asyncio
import logging

import pandas as pd
import prettytable
from backtesting import Backtest
from kraken.spot import Market


def get_historical_data(pair: str, interval: str = "60") -> pd.DataFrame:
    """
    Fetch historical OHLC data for a given cryptocurrency pair and interval.

    Args:
        pair (str): The cryptocurrency pair, e.g., 'XXBTZUSD'. interval (str):
        The interval in minutes, e.g., '60' for 60 minutes or '1440' for one
        day.

    Returns:
        pd.DataFrame: A DataFrame containing the OHLC data.
    """
    df = pd.DataFrame(
        Market().get_ohlc(pair=pair, interval=interval)[pair],  # 720 entries
        columns=["time", "open", "high", "low", "close", "vwap", "volume", "count"],
    ).astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


async def main() -> None:
    """
    Main function to perform backtesting and find the optimal interval for the
    grid trading strategy.
    """
    data = get_historical_data("XXBTZEUR")
    amount_per_grid = 25  # EUR
    fee = 0.0026
    interval = 0.001  # Should be > fee * 2
    initial_hold = 10000000.0
    results = {}

    while (interval := interval + 0.001) <= 0.04:
        bt = Backtest(
            strategy_config={
                "strategy": "GridHODL",
                "userref": 1,
                "name": "Intervaltester",
                "interval": interval,
                "amount_per_grid": amount_per_grid,
                "max_investment": 1000000,
                "n_open_buy_orders": 3,
                "base_currency": "BTC",
                "quote_currency": "EUR",
                "fee": fee,
            },
            db_config={"sqlite_file": ":memory:"},
            balances={
                "balances": {
                    "XXBT": {"balance": "0.0", "hold_trade": "0.0"},
                    "ZEUR": {"balance": str(initial_hold), "hold_trade": "0.0"},
                },
            },
        )
        try:
            await bt.run(prices=data["close"])
        finally:
            await bt.instance.async_close()
            await bt.instance.stop()
            bt.compute_summary()
            results[interval] = {
                "market_price": bt.summary_market_price,
                "n_buys": bt.api.n_exec_buy_orders,
                "n_sells": bt.api.n_exec_sell_orders,
                bt.instance.base_currency: bt.summary_balances[bt.api.base],
                bt.instance.quote_currency: bt.summary_balances[bt.api.quote],
            }

    table = prettytable.PrettyTable()
    table.field_names = [
        "Interval",
        f"Market Price ({bt.instance.quote_currency})",
        "N Sells",
        "N Buys",
        f"Trade volume ({bt.instance.quote_currency})",
        "Volume-based profit",
        f"{bt.instance.base_currency} (total)",
        f"{bt.instance.base_currency} (hold trade)",
        f"{bt.instance.quote_currency} (total)",
        f"{bt.instance.quote_currency} (hold trade)",
    ]

    for interval, data in dict(
        sorted(results.items(), key=lambda x: x[1]["market_price"], reverse=True),
    ).items():
        table.add_row(
            [
                f"{interval:.4f} ({interval * 100:.2f}%)",
                f"{data['market_price']:.4f}",
                data["n_sells"],
                data["n_buys"],
                (trade_volume := (data["n_buys"] + data["n_sells"]) * amount_per_grid),
                f"{((data['market_price'] - initial_hold) / trade_volume) * 100:.4f}%",
                data[bt.instance.base_currency]["balance"],
                data[bt.instance.base_currency]["hold_trade"],
                data[bt.instance.quote_currency]["balance"],
                data[bt.instance.quote_currency]["hold_trade"],
            ],
        )
    print("\nResults (sorted by Market Price):")
    print(table)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)8s | %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
        level=logging.WARNING,
    )
    asyncio.run(main())
