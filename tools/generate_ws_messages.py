#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

import json
import random
from pathlib import Path


def generate_ticker_events(
    symbol: str,
    price_range: tuple[float, float],
    num_events: int,
) -> list[dict]:
    events = []
    current_price = random.uniform(*price_range)

    for _ in range(num_events):
        bid = round(current_price, 2)
        ask = round(current_price + random.uniform(0.1, 1.0), 2)
        bid_qty = round(random.uniform(0.1, 1.0), 8)
        ask_qty = round(random.uniform(0.1, 1.0), 8)
        last = bid
        volume = round(random.uniform(1000, 5000), 8)
        vwap = round(random.uniform(price_range[0], price_range[1]), 1)
        low = round(min(price_range[0], current_price - random.uniform(0, 5000)), 1)
        high = round(max(price_range[1], current_price + random.uniform(0, 5000)), 1)
        change = round(last - current_price, 1)
        change_pct = round((change / current_price) * 100, 2)

        event = {
            "channel": "ticker",
            "type": "update",
            "data": [
                {
                    "symbol": symbol,
                    "bid": bid,
                    "bid_qty": bid_qty,
                    "ask": ask,
                    "ask_qty": ask_qty,
                    "last": last,
                    "volume": volume,
                    "vwap": vwap,
                    "low": low,
                    "high": high,
                    "change": change,
                    "change_pct": change_pct,
                },
            ],
        }

        events.append(event)

        # Update current price for next event
        current_price += random.uniform(-1000, 1000)
        current_price = max(price_range[0], min(price_range[1], current_price))

    return events


def main() -> None:

    symbol = "BTC/EUR"
    price_range = (50000, 100000)
    num_events = 1000000

    # Generate events
    events = generate_ticker_events(symbol, price_range, num_events)

    with Path("generated_ticker_events.json").open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")

    print(f"Generated {num_events} ticker events.")


if __name__ == "__main__":
    main()
