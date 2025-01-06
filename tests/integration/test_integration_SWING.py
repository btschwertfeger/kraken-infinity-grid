#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

""" GridSell Integration test for SWING strategy.

TODOs:

- [ ] Check for unfilled surplus due to partly filled buy orders
"""

import logging
from unittest import mock

import pytest

from kraken_infinity_grid.gridbot import KrakenInfinityGridBot


@pytest.fixture
def config() -> dict:
    """Fixture to create a mock configuration."""
    return {
        "strategy": "SWING",
        "userref": 123456789,
        "name": "TestBot",
        "interval": 0.01,
        "amount_per_grid": 100,
        "max_investment": 10000,
        "n_open_buy_orders": 5,
        "base_currency": "BTC",
        "quote_currency": "USD",
        "telegram_token": "telegram_token",
        "telegram_chat_id": "telegram_chat_id",
        "exception_token": "exception_token",
        "exception_chat_id": "exception_chat_id",
    }


@pytest.mark.integration
@pytest.mark.asyncio
@mock.patch("kraken_infinity_grid.order_management.sleep", return_value=None)
@mock.patch("kraken_infinity_grid.gridbot.sleep", return_value=None)
async def test_integration_SWING(  # noqa: C901
    mock_sleep_gridbot: mock.Mock,  # noqa: ARG001
    mock_sleep_order_management: mock.Mock,  # noqa: ARG001
    instance: KrakenInfinityGridBot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Integration test for the SWING strategy using pre-generated websocket
    messages.
    """
    caplog.set_level(logging.INFO)

    # Mock the initial setup
    instance.market.get_ticker.return_value = {"XXBTZUSD": {"c": ["50000.0"]}}

    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 50000.0}],
        },
    )
    assert not instance.is_ready_to_trade

    # ==========================================================================
    # During the following processing, the following steps are done:
    # 1. The algorithm prepares for trading (see setup)
    # 2. The order manager checks the price range
    # 3. The order manager checks for n open buy orders
    # 4. The order manager places new orders
    await instance.on_message(
        {
            "channel": "executions",
            "type": "snapshot",
            "data": [{"exec_type": "canceled", "order_id": "txid0"}],
        },
    )

    # The algorithm should already be ready to trade
    assert instance.is_ready_to_trade

    # ==========================================================================
    # 1. PLACEMENT OF INITIAL N BUY ORDERS
    # After both fake-websocket channels are connected, the algorithm went
    # through its full setup and placed orders against the fake Kraken API and
    # finally saved those results into the local orderbook table.
    #
    # The SWING strategy additionally starts selling the existing base currency
    # at defined intervals.
    current_orders = instance.orderbook.get_orders().all()
    assert len(current_orders) == 6

    # Check if the five initial buy orders are placed with the expected price
    # and volume. Note that the interval is not exactly 0.01 due to the fee
    # which is taken into account. We also see the first sell order using
    # existing BTC to sell.
    for order, price, volume, side in zip(
        current_orders,
        [49504.9, 49014.7, 48529.4, 48048.9, 47573.1, 51005.0],
        [0.00202, 0.0020402, 0.0020606, 0.00208121, 0.00210202, 0.00197044],
        ["buy"] * 5 + ["sell"],
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.price == price
        assert order.volume == volume
        assert order.side == side

    # ==========================================================================
    # 2. RAPID PRICE DROP - FILLING ALL BUY ORDERS + CREATING SELL ORDERS
    # Now check the behavior for a rapid price drop.
    # It should fill the buy orders and place 6 new sell orders.
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 40000.0}],
        },
    )
    assert instance.ticker.last == 40000.0
    for order in instance.orderbook.get_orders().all():
        if order.side == "buy":
            instance.trade.fill_order(order.txid)
            await instance.on_message(
                {
                    "channel": "executions",
                    "type": "update",
                    "data": [{"exec_type": "filled", "order_id": order.txid}],
                },
            )

    current_orders = instance.orderbook.get_orders().all()
    assert len(current_orders) == 6
    for order, price, volume in zip(
        current_orders,
        [51005.0, 49999.9, 49504.8, 49014.6, 48529.3, 48048.8],
        [0.00197044, 0.00201005, 0.00203015, 0.00205046, 0.00207096, 0.00209167],
        strict=True,
    ):
        assert order.side == "sell"
        assert order.price == price
        assert order.volume == volume

    # ==========================================================================
    # 3. NEW TICKER TO ENSURE N OPEN BUY ORDERS
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 40000.1}],
        },
    )
    current_orders = instance.orderbook.get_orders().all()
    assert len(current_orders) == 11

    for order, price, volume in zip(
        (o for o in current_orders if o.side == "sell"),
        [51005.0, 49999.9, 49504.8, 49014.6, 48529.3, 48048.8],
        [0.00197044, 0.00201005, 0.00203015, 0.00205046, 0.00207096, 0.00209167],
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume

    for order, price, volume in zip(
        (o for o in current_orders if o.side == "buy"),
        [39604.0, 39211.8, 38823.5, 38439.1, 38058.5],
        [0.00252499, 0.00255025, 0.00257575, 0.00260151, 0.00262753],
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume

    # ==========================================================================
    # 4. FILLING SELL ORDERS WHILE SHIFTING UP BUY ORDERS
    # Check if shifting up the buy orders works
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 60000.0}],
        },
    )
    assert instance.ticker.last == 60000.0
    for order in instance.orderbook.get_orders().all():
        if order.side == "sell":
            instance.trade.fill_order(order.txid)
            await instance.on_message(
                {
                    "channel": "executions",
                    "type": "update",
                    "data": [{"exec_type": "filled", "order_id": order.txid}],
                },
            )

    # We should now still have 10 buy orders, 5 of the already existing ones and
    # 5 based on the executed sell orders.
    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        [
            59405.9,
            58817.7,
            58235.3,
            57658.7,
            57087.8,
            50500.0,
            49504.8,
            49014.6,
            48529.3,
            48048.8,
        ],
        [
            0.00168333,
            0.00170016,
            0.00171717,
            0.00173434,
            0.00175168,
            0.00198019,
            0.00202,
            0.0020402,
            0.00206061,
            0.00208121,
        ],
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.side == "buy"

    # ==========================================================================
    # 5. ENSURING THAT ONLY N BUY ORDERS EXIST
    #    ... the highest n buy orders ...

    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 60000.1}],
        },
    )

    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        [59405.9, 58817.7, 58235.3, 57658.7, 57087.8],
        [0.00168333, 0.00170016, 0.00171717, 0.00173434, 0.00175168],
        strict=False,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.volume == volume
