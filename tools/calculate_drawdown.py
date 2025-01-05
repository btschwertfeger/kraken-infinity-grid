#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""
Calculate maximum drawdown for grid trading strategy.

Example:
    python calculate_drawdown.py \
        --price 100000 \
        --interval 0.02 \
        --amount 20 \
        --max-investment 500

    === Grid Trading Drawdown Calculator ===
    Starting price: 100000.00
    Interval: 2.0%
    Amount per grid: 20.00
    Maximum investment: 100.00

    Grid Levels:
    Grid 1: 98000.00 (-2.00%)
    Grid 2: 96040.00 (-3.96%)
    Grid 3: 94119.20 (-5.88%)
    Grid 4: 92236.82 (-7.76%)
    Grid 5: 90392.08 (-9.61%)

    Maximum drawdown: 9.6%
"""

import argparse
from typing import List, Tuple


def calculate_grid_levels(
    current_price: float,
    interval: float,
    amount_per_grid: float,
    max_investment: float,
) -> Tuple[List[float], float, float]:
    """Calculate grid levels and maximum drawdown."""

    # Calculate maximum number of grids
    max_grids = int(max_investment / amount_per_grid)

    # Calculate price levels
    price_levels = []
    total_investment = 0
    price = current_price

    for _ in range(max_grids):
        price *= 1 - interval
        price_levels.append(price)
        total_investment += amount_per_grid

    # Calculate drawdown
    max_drawdown_pct = (current_price - price_levels[-1]) / current_price * 100

    return price_levels, max_drawdown_pct


def main() -> None:
    """Main function"""
    parser = argparse.ArgumentParser(description="Calculate grid trading drawdown")
    parser.add_argument("--price", type=float, required=True, help="Current price")
    parser.add_argument(
        "--interval",
        type=float,
        required=True,
        help="Grid interval (e.g. 0.02 for 2%)",
    )
    parser.add_argument("--amount", type=float, required=True, help="Amount per grid")
    parser.add_argument(
        "--max-investment",
        type=float,
        required=True,
        help="Maximum investment",
    )

    args = parser.parse_args()

    levels, drawdown_pct, _ = calculate_grid_levels(
        args.price,
        args.interval,
        args.amount,
        args.max_investment,
    )

    print("\n=== Grid Trading Drawdown Calculator ===")
    print(f"Starting price: {args.price:.2f}")
    print(f"Interval: {args.interval * 100:.1f}%")
    print(f"Amount per grid: {args.amount:.2f}")
    print(f"Maximum investment: {args.max_investment:.2f}")
    print("\nGrid Levels:")
    for i, price in enumerate(levels, 1):
        print(f"Grid {i}: {price:.2f} (-{(1 - price / args.price) * 100:.2f}%)")

    print(f"\nMaximum drawdown: {drawdown_pct:.1f}%")


if __name__ == "__main__":
    main()
