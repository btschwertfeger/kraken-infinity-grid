#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Integration test for the DCA strategy."""

import logging
from unittest import mock

import pytest

from kraken_infinity_grid.gridbot import KrakenInfinityGridBot


@pytest.fixture
def config() -> dict:
    """Fixture to create a mock configuration."""
    return {
        "strategy": "DCA",
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


@pytest.mark.asyncio
@mock.patch("kraken_infinity_grid.order_management.sleep", return_value=None)
@mock.patch("kraken_infinity_grid.gridbot.sleep", return_value=None)
async def test_integration_DCA(  # noqa: PLR0915
    mock_sleep_gridbot: mock.Mock,  # noqa: ARG001
    mock_sleep_order_management: mock.Mock,  # noqa: ARG001
    instance: KrakenInfinityGridBot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Integration test for DCA strategy using pre-generated websocket messages.
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

    # Check if the five initial buy orders are placed with the expected price
    # and volume. Note that the interval is not exactly 0.01 due to the fee
    # which is taken into account.
    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        [49504.9, 49014.7, 48529.4, 48048.9, 47573.1],
        [0.00202, 0.0020402, 0.0020606, 0.00208121, 0.00210202],
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.side == "buy"
        assert order.price == price
        assert order.volume == volume

    assert instance.orderbook.count() == 5

    # ==========================================================================
    # 2. SHIFTING UP BUY ORDERS
    # Check if shifting up the buy orders works
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 60000.0}],
        },
    )

    # We should now still have 5 buy orders, but at a higher price. The other
    # orders should be canceled.
    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        [59405.9, 58817.7, 58235.3, 57658.7, 57087.8],
        [0.00168333, 0.00170016, 0.00171717, 0.00173434, 0.00175168],
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.side == "buy"
        assert order.price == price
        assert order.volume == volume

    assert instance.orderbook.count() == 5

    # ==========================================================================
    # 3. FILLING A BUY ORDER
    # Now lets let the price drop a bit so that a buy order gets triggered.
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 59000.0}],
        },
    )

    # Quick re-check ... the price update should not affect any orderbook
    # changes when dropping.
    current_orders = instance.orderbook.get_orders().all()
    for order, price, volume in zip(
        current_orders,
        [59405.9, 58817.7, 58235.3, 57658.7, 57087.8],
        [0.00168333, 0.00170016, 0.00171717, 0.00173434, 0.00175168],
        strict=False,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.side == "buy"
        assert order.price == price
        assert order.volume == volume

    # Now trigger the execution of the first buy order
    instance.trade.fill_order(current_orders[0].txid)  # fill in "upstream"
    await instance.on_message(  # notify downstream
        {
            "channel": "executions",
            "type": "update",
            "data": [{"exec_type": "filled", "order_id": current_orders[0].txid}],
        },
    )
    assert instance.orderbook.count() == 4

    # Ensure that we have 4 buy orders and *no* sell order
    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        [58817.7, 58235.3, 57658.7, 57087.8],
        [0.00170016, 0.00171717, 0.00173434, 0.00175168],
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.volume == volume
        assert order.side == "buy"

    assert instance.orderbook.count() == 4

    # ==========================================================================
    # 4. ENSURING N OPEN BUY ORDERS
    # If there is a new price event, the algorithm will place the 5th buy order.
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 59100.0}],
        },
    )
    for order, price, volume, side in zip(
        instance.orderbook.get_orders().all(),
        [58817.7, 58235.3, 57658.7, 57087.8, 56522.5],
        [0.00170016, 0.00171717, 0.00173434, 0.00175168, 0.0017692],
        ["buy"] * 5,
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.volume == volume
        assert order.side == side

    assert instance.orderbook.count() == 5

    # ==========================================================================
    # 5. RAPID PRICE DROP - FILLING ALL BUY ORDERS
    # Now check the behavior for a rapid price drop.
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 50000.0}],
        },
    )
    assert instance.ticker.last == 50000.0
    for order in instance.orderbook.get_orders().all():
        instance.trade.fill_order(order.txid)
        await instance.on_message(
            {
                "channel": "executions",
                "type": "update",
                "data": [{"exec_type": "filled", "order_id": order.txid}],
            },
        )
    current_orders = instance.orderbook.get_orders().all()
    assert len(current_orders) == 0
    assert instance.orderbook.count() == 0

    # ==========================================================================
    # 6. ENSURE N OPEN BUY ORDERS
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [{"symbol": "BTC/USD", "last": 50100.0}],
        },
    )
    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        [49603.9, 49112.7, 48626.4, 48144.9, 47668.2],
        [0.00201597, 0.00203613, 0.00205649, 0.00207706, 0.00209783],
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.side == "buy"
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.volume == volume

    assert instance.orderbook.count() == 5
