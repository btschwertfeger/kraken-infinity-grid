# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

""" GridSell Integration test for SWING strategy. """

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
async def test_integration_SWING(
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

    await instance.trade.on_ticker_update(instance.on_message, 50000.0)
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
        (49504.9, 49014.7, 48529.4, 48048.9, 47573.1, 51005.0),
        (0.00202, 0.0020402, 0.0020606, 0.00208121, 0.00210202, 0.00197044),
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
    await instance.trade.on_ticker_update(instance.on_message, 40000.0)
    assert instance.ticker.last == 40000.0

    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        (51005.0, 49999.9, 49504.8, 49014.6, 48529.3, 48048.8),
        (0.00197044, 0.00201005, 0.00203015, 0.00205046, 0.00207096, 0.00209167),
        strict=True,
    ):
        assert order.side == "sell"
        assert order.price == price
        assert order.volume == volume

    # ==========================================================================
    # 3. NEW TICKER TO ENSURE N OPEN BUY ORDERS
    await instance.trade.on_ticker_update(instance.on_message, 40000.1)
    current_orders = instance.orderbook.get_orders().all()
    assert len(current_orders) == 11

    for order, price, volume in zip(
        (o for o in current_orders if o.side == "sell"),
        (51005.0, 49999.9, 49504.8, 49014.6, 48529.3, 48048.8),
        (0.00197044, 0.00201005, 0.00203015, 0.00205046, 0.00207096, 0.00209167),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume

    for order, price, volume in zip(
        (o for o in current_orders if o.side == "buy"),
        (39604.0, 39211.8, 38823.5, 38439.1, 38058.5),
        (0.00252499, 0.00255025, 0.00257575, 0.00260151, 0.00262753),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume

    # ==========================================================================
    # 4. FILLING SELL ORDERS WHILE SHIFTING UP BUY ORDERS
    # Check if shifting up the buy orders works
    await instance.trade.on_ticker_update(instance.on_message, 60000.0)
    assert instance.ticker.last == 60000.0

    # We should now still have 5 buy orders.
    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        (59405.9, 58817.7, 58235.3, 57658.7, 57087.8),
        (0.00168333, 0.00170016, 0.00171717, 0.00173434, 0.00175168),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.side == "buy"


@pytest.mark.integration
@pytest.mark.asyncio
@mock.patch("kraken_infinity_grid.order_management.sleep", return_value=None)
@mock.patch("kraken_infinity_grid.gridbot.sleep", return_value=None)
async def test_integration_SWING_unfilled_surplus(
    mock_sleep_gridbot: mock.Mock,  # noqa: ARG001
    mock_sleep_order_management: mock.Mock,  # noqa: ARG001
    instance: KrakenInfinityGridBot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Integration test for the SWING strategy using pre-generated websocket
    messages.

    This test checks if the unfilled surplus is handled correctly.

    unfilled surplus: The base currency volume that was partly filled by an buy
    order, before the order was cancelled.
    """
    caplog.set_level(logging.INFO)

    # Mock the initial setup
    instance.market.get_ticker.return_value = {"XXBTZUSD": {"c": ["50000.0"]}}

    await instance.trade.on_ticker_update(instance.on_message, 50000.0)
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
    for order, price, volume, side in zip(
        instance.orderbook.get_orders().all(),
        (49504.9, 49014.7, 48529.4, 48048.9, 47573.1, 51005.0),
        (0.00202, 0.0020402, 0.0020606, 0.00208121, 0.00210202, 0.00197044),
        ["buy"] * 5 + ["sell"],
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == side
        assert order.symbol == "BTCUSD"
        assert order.userref == instance.userref

    balances = instance.trade.get_balances()
    assert float(balances["XXBT"]["balance"]) == pytest.approx(99.99802956)
    assert float(balances["XXBT"]["hold_trade"]) == pytest.approx(0.00197044)
    assert float(balances["ZUSD"]["balance"]) == pytest.approx(999500.0011705891)
    assert float(balances["ZUSD"]["hold_trade"]) == pytest.approx(499.99882941100003)

    # ==========================================================================
    # 2. BUYING PARTLY FILLED and ensure that the unfilled surplus is handled
    instance.trade.fill_order(instance.orderbook.get_orders().first().txid, 0.002)
    assert instance.orderbook.count() == 6

    # We have not 100.002 here, since the GridSell is initially creating a sell
    # order which reduces the available base balance.
    balances = instance.trade.get_balances()
    assert float(balances["XXBT"]["balance"]) == pytest.approx(100.00002956)
    assert float(balances["XXBT"]["hold_trade"]) == pytest.approx(0.00197044)
    assert float(balances["ZUSD"]["balance"]) == pytest.approx(999400.9913705891)
    assert float(balances["ZUSD"]["hold_trade"]) == pytest.approx(400.98902941100005)

    instance.om.handle_cancel_order(
        instance.orderbook.get_orders().first().txid,
    )

    assert instance.configuration.get()["vol_of_unfilled_remaining"] == 0.002
    assert (
        instance.configuration.get()["vol_of_unfilled_remaining_max_price"] == 49504.9
    )

    # ==========================================================================
    # 3. SELLING THE UNFILLED SURPLUS
    #    The sell-check is done only during cancelling orders, as this is the
    #    only time where this amount is touched. So we need to create another
    #    partly filled order.

    instance.om.new_buy_order(49504.9)
    assert len(instance.trade.get_open_orders()["open"]) == 6

    order = next(o for o in instance.orderbook.get_orders().all() if o.price == 49504.9)
    instance.trade.fill_order(order["txid"], 0.002)
    instance.om.handle_cancel_order(order["txid"])

    # We will have 6 orders, 2 sell and 3 buy. We don't have 5 buy orders since
    # we don't triggered the price update.
    assert len(instance.trade.get_open_orders()["open"]) == 6
    # Ensure that the unfilled surplus is now 0.0
    assert instance.configuration.get()["vol_of_unfilled_remaining"] == 0.0

    # Get the sell order that was placed as extra sell order. This one is
    # 'interval' above the the highest buy price.
    sell_orders = instance.orderbook.get_orders(filters={"side": "sell", "id": 7}).all()
    assert sell_orders[0].price == 50500.0
    assert sell_orders[0].volume == pytest.approx(0.00199014)

    # ==========================================================================
    # 4. MAX INVESTMENT REACHED

    # First ensure that new buy orders can be placed...
    assert not instance.max_investment_reached
    instance.om.cancel_all_open_buy_orders()
    assert instance.orderbook.count() == 2  # two sell orders
    await instance.trade.on_ticker_update(instance.on_message, 50000.0)
    assert instance.orderbook.count() == 7  # 2 sell, 5 buy

    # Now with a different max investment, the max investment should be reached
    # and no further orders be placed.
    assert not instance.max_investment_reached
    instance.max_investment = 202  # 200 USD + fee
    instance.om.cancel_all_open_buy_orders()
    assert instance.orderbook.count() == 2
    await instance.trade.on_ticker_update(instance.on_message, 50000.0)
    assert instance.orderbook.count() == 2
    assert instance.max_investment_reached
