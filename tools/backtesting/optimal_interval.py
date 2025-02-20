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
Data time range: 2025-01-12 08:00:00 to 2025-02-11 07:00:00
+----------------+--------------------+---------+--------+--------------------+---------------------+-----------------------+------------------------+-------------------+-------------------+
|    Interval    | Market Price (EUR) | N Sells | N Buys | Trade volume (EUR) | Volume-based profit |      BTC (total)      |    BTC (hold trade)    |    EUR (total)    |  EUR (hold trade) |
+----------------+--------------------+---------+--------+--------------------+---------------------+-----------------------+------------------------+-------------------+-------------------+
| 0.0210 (2.10%) |    1000005.4665    |    18   |   24   |        1050        |       0.5206%       | 0.0016282999999999998 |       0.00150382       | 999849.9654728107 | 75.54282935119095 |
| 0.0220 (2.20%) |    1000005.2172    |    17   |   22   |        975         |       0.5351%       |       0.00136391      |       0.00124384       | 999874.9652039555 | 75.51128815186323 |
| 0.0330 (3.30%) |    1000004.3978    |    8    |   10   |        450         |       0.9773%       | 0.0005697400000000001 | 0.0004874100000000001  | 999949.9881832895 | 75.24845152932751 |
| 0.0200 (2.00%) |    1000004.3962    |    17   |   23   |        1000        |       0.4396%       | 0.0016170800000000001 |       0.00150357       | 999849.9667006223 | 75.49813897806229 |
| 0.0250 (2.50%) |    1000003.4176    |    11   |   16   |        675         |       0.5063%       | 0.0013450100000000002 | 0.0012453400000000002  | 999874.9704892357 | 75.36020184157425 |
| 0.0350 (3.50%) |    1000003.1625    |    6    |   8    |        350         |       0.9036%       |       0.0005568       | 0.00048724999999999994 | 999949.9886699338 | 75.19879946928025 |
| 0.0310 (3.10%) |    1000003.1294    |    7    |   11   |        450         |       0.6954%       |       0.00108014      |       0.00099589       | 999899.9771240605 | 75.25522636289202 |
| 0.0230 (2.30%) |    1000003.1137    |    12   |   17   |        725         |       0.4295%       | 0.0013418300000000002 |       0.00124484       | 999874.9703002557 | 75.40516251525602 |
| 0.0260 (2.60%) |    1000003.0944    |    10   |   15   |        625         |       0.4951%       | 0.0013416300000000001 |       0.00124435       |  999874.970116059 | 75.35526006792955 |
| 0.0340 (3.40%) |    1000002.9820    |    6    |   8    |        350         |       0.8520%       | 0.0005549099999999999 | 0.0004874100000000001  | 999949.9886272204 | 75.19853153376624 |
| 0.0240 (2.40%) |    1000002.4204    |    10   |   15   |        625         |       0.3873%       |       0.00133455      | 0.0012450900000000001  | 999874.9721661004 |  75.3363423329422 |
| 0.0270 (2.70%) |    1000002.3290    |    8    |   13   |        525         |       0.4436%       | 0.0013336099999999998 |       0.00124651       | 999874.9705948302 | 75.30492621440575 |
| 0.0300 (3.00%) |    1000002.0550    |    6    |   10   |        400         |       0.5138%       |       0.0010689       | 0.0009940599999999997  | 999899.9761401109 |  75.249501106859  |
| 0.0280 (2.80%) |    1000002.0340    |    7    |   12   |        475         |       0.4282%       | 0.0013305300000000003 |       0.00124677       | 999874.9697224711 | 75.27950104504197 |
| 0.0320 (3.20%) |    1000001.9165    |    5    |   9    |        350         |       0.5476%       |       0.00106743      | 0.0009958900000000001  | 999899.9779652994 | 75.22375147674826 |
| 0.0290 (2.90%) |    1000001.8094    |    6    |   10   |        400         |       0.4524%       | 0.0010662999999999998 |       0.00099406       | 999899.9788310586 | 75.24885925780153 |
| 0.0370 (3.70%) |    1000001.3350    |    3    |   6    |        225         |       0.5933%       |       0.00079951      | 0.0007450200000000001  | 999924.9826145548 |  75.1676288614165 |
| 0.0390 (3.90%) |    1000001.0436    |    2    |   5    |        175         |       0.5963%       |       0.00079645      | 0.0007480900000000001  | 999924.9833821958 | 75.14193082649103 |
| 0.0380 (3.80%) |    1000000.7396    |    2    |   5    |        175         |       0.4226%       |       0.00079327      | 0.0007462600000000001  |  999924.983137572 | 75.14208339901779 |
| 0.0360 (3.60%) |    1000000.7305    |    3    |   6    |        225         |       0.3246%       | 0.0007931699999999999 |       0.00074036       |  999924.983513722 |  75.1674896032595 |
+----------------+--------------------+---------+--------+--------------------+---------------------+-----------------------+------------------------+-------------------+-------------------+
"""

import asyncio
import logging
import warnings

import pandas as pd
import prettytable
from backtesting import Backtest
from kraken.spot import Market

warnings.filterwarnings("ignore", category=DeprecationWarning)


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
    df = get_historical_data("XXBTZEUR")
    amount_per_grid = 25  # Quote currency
    fee = 0.00025  # FIXME: Values near zero doesn't work.
    step = 0.001
    interval = 0.02 - step  # Should be larger than fee * 2
    initial_hold = 1000000.0
    results = {}

    while (interval := interval + step) <= 0.04:
        bt = Backtest(
            strategy_config={
                "strategy": "GridHODL",
                "userref": 1,
                "name": "Intervaltester",
                "interval": interval,
                "amount_per_grid": amount_per_grid,
                "max_investment": initial_hold,
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
            await bt.run(prices=df["close"])
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
        trade_volume = (data["n_buys"] + data["n_sells"]) * amount_per_grid
        volume_based_profit = (
            "0.0000%"
            if trade_volume == 0
            else f"{((data['market_price'] - initial_hold) / trade_volume) * 100:.4f}%"
        )
        table.add_row(
            [
                f"{interval:.4f} ({interval * 100:.2f}%)",
                f"{data['market_price']:.4f}",
                data["n_sells"],
                data["n_buys"],
                trade_volume,
                volume_based_profit,
                data[bt.instance.base_currency]["balance"],
                data[bt.instance.base_currency]["hold_trade"],
                data[bt.instance.quote_currency]["balance"],
                data[bt.instance.quote_currency]["hold_trade"],
            ],
        )

    print("\nResults (sorted by Market Price):")
    print(f"Data time range: {df['time'].iloc[0]} to {df['time'].iloc[-1]}")
    print(table)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)8s | %(message)s",
        datefmt="%Y/%m/%d %H:%M:%S",
        level=logging.WARNING,
    )
    asyncio.run(main())
