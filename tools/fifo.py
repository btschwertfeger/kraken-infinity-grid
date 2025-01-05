#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

""" FIFO PnL calculation for Kraken trades.

This script allows to calculate the FIFO PnL for a given trading pair on Kraken.
Filters can be applied to the trades by specifying a start and end date, as well
as a user reference id, allowing for easy tax reporting.

Example Usage:
    python fifo.py --symbol XXBTZUSD --start 2023-01-01 --userref 1734531950
"""

# NOTE: This only works for trades on Kraken and does not respect "buys" from
#       other exchanges, transfers, and so on. This is only intended to be used
#       for the KrakenInfinityGridBot in order to determine the PnL of the
#       trades made by the individual bots.

import argparse
import os
import sys
from collections import deque
from datetime import datetime
from decimal import Decimal
from operator import itemgetter

from kraken.spot import User


def compute_fifo_pnl(trades: dict) -> dict:  # noqa: PLR0914
    """Compute FIFO PnL for a list of trades."""
    fifo_queue = deque()
    realized_pnl = Decimal(0)
    unrealized_pnl = Decimal(0)
    balance = Decimal(0)

    for trade in trades:
        side = trade["type"]
        amount = Decimal(trade["vol"])  # BTC amount
        price = Decimal(trade["price"])  # Price in EUR per BTC
        fee = Decimal(trade["fee"])  # Fee in EUR

        if side == "buy":
            # Add the cost of the BTC (including fee) to the queue
            total_cost = (amount * price) + fee
            fifo_queue.append((amount, total_cost))
            balance += amount

        elif side == "sell":
            # Calculate realized P&L
            sell_proceeds = (amount * price) - fee
            cost_basis = Decimal(0)
            base_currency_to_sell = amount

            # Match sales to FIFO purchases
            while base_currency_to_sell > 0 and fifo_queue:
                fifo_amount, fifo_cost = fifo_queue.popleft()
                if fifo_amount <= base_currency_to_sell:
                    # Use entire FIFO lot
                    cost_basis += fifo_cost
                    base_currency_to_sell -= fifo_amount
                else:
                    # Partially use FIFO lot
                    partial_cost = (fifo_cost / fifo_amount) * base_currency_to_sell
                    cost_basis += partial_cost
                    fifo_queue.appendleft(
                        (fifo_amount - base_currency_to_sell, fifo_cost - partial_cost),
                    )
                    base_currency_to_sell = 0

            # Calculate P&L for this sale
            pnl = sell_proceeds - cost_basis
            realized_pnl += pnl
            balance -= amount

    # Calculate unrealized P&L
    unrealized_pnl = sum(
        (price - (lot_cost / lot_amount)) * lot_amount
        for lot_amount, lot_cost in fifo_queue
    )

    return {
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "balance": balance,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute FIFO PnL for Kraken trades.",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        required=True,
        help="Trading pair symbol (e.g., XXBTZEUR)",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date for filtering trades (e.g., 2023-01-01)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date for filtering trades (e.g., 2023-12-31)",
    )
    parser.add_argument(
        "--userref",
        type=int,
        help="A user reference id to filter trades",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Generate a CSV file listing the trades.",
    )
    args = parser.parse_args()
    if not (api_key := os.getenv("KRAKEN_API_KEY")) or not (
        secret_key := os.getenv("KRAKEN_SECRET_KEY")
    ):
        print("ERROR: 'KRAKEN_API_KEY' and 'KRAKEN_SECRET_KEY' must be set!")
        sys.exit()

    # ==========================================================================
    # Retrieve and filter trades from Kraken Exchange
    start = (
        None
        if not args.start
        else datetime.timestamp(datetime.strptime(args.start, "%Y-%m-%d"))
    )
    end = (
        None
        if not args.end
        else datetime.timestamp(datetime.strptime(args.end, "%Y-%m-%d"))
    )
    user = User(api_key, secret_key)
    trades = user.get_trades_history(start=start, end=end)

    filtered_trades = [
        trade for trade in trades["trades"].values() if trade["pair"] == args.symbol
    ]
    filtered_trades.sort(key=itemgetter("time"))

    if args.userref:
        users_orders = user.get_closed_orders(
            start=start,
            end=end,
            userref=args.userref,
        )
        for trade in filtered_trades.copy():
            if trade["ordertxid"] not in users_orders["closed"]:
                filtered_trades.remove(trade)

    results = compute_fifo_pnl(filtered_trades)

    # ==========================================================================
    if args.csv:
        import csv  # noqa: PLC0415
        from datetime import timezone  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        for entry in filtered_trades:
            entry["time"] = datetime.fromtimestamp(
                entry["time"],
                tz=timezone.utc,
            ).strftime("%Y-%m-%d %H:%M:%S %Z")

        with Path("trades.csv").open(mode="w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=filtered_trades[0].keys())
            writer.writeheader()
            writer.writerows(filtered_trades)

    # ==========================================================================
    # Print the results
    print("*" * 36 + " Trades " + "*" * 36)
    for trade in filtered_trades:
        print(trade)
    print("*" * 80)
    print(f"Found {trades['count']} trades between {args.start} and {args.end}")
    print(f"Found {len(filtered_trades)} trades for {args.symbol}")
    print(f"Realized PnL: {results['realized_pnl']}")
    print(f"Unrealized PnL: {results['unrealized_pnl']}")
    print(f"Balance: {results['balance']}")


if __name__ == "__main__":
    main()
