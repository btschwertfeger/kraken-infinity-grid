# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

""" GridSell Integration test for GridSell strategy. """

import logging
from unittest import mock

import pytest

from kraken_infinity_grid.gridbot import KrakenInfinityGridBot


@pytest.fixture
def config() -> dict:
    """Fixture to create a mock configuration."""
    return {
        "strategy": "GridSell",
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
async def test_integration_GridSell(  # noqa: PLR0915
    mock_sleep_gridbot: mock.Mock,  # noqa: ARG001
    mock_sleep_order_management: mock.Mock,  # noqa: ARG001
    instance: KrakenInfinityGridBot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Integration test for the GridSell strategy using pre-generated websocket
    messages.

    This test simulates the full trading process of the trading algorithm, by
    leveraging a mocked Kraken API in order to verify interactions between the
    API, the algorithm and database. The test tries to cover almost all cases
    that could happen during the trading process.

    It tests:

    * Handling of ticker updates
    * Handling of execution updates
    * Initialization after the ticker and execution channels are connected
    * Placing of buy orders and shifting them up
    * Execution of buy orders and placement of corresponding sell orders
    * Execution of sell orders
    * Full database interactions using SQLite

    It does not cover the following cases:

    * Interactions related to telegram notifications
    * Initialization of the algorithm
    * Command-line interface / user-like interactions

    This one contains a lot of copy-paste, but hopefully doesn't need to get
    touched anymore.
    """
    caplog.set_level(logging.INFO)

    # Mock the initial setup
    instance.market.get_ticker.return_value = {"XXBTZUSD": {"c": ["50000.0"]}}

    await instance.trade.on_ticker_update(instance.on_message, 50000.0)
    assert not instance.state_machine.facts["ready_to_trade"]

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
    assert instance.state_machine.facts["ready_to_trade"]

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
        assert order.price == price
        assert order.volume == volume
        assert order.side == "buy"
        assert order.symbol == "BTCUSD"
        assert order.userref == instance.userref

    assert instance.orderbook.count() == 5

    # ==========================================================================
    # 2. SHIFTING UP BUY ORDERS
    # Check if shifting up the buy orders works
    await instance.trade.on_ticker_update(instance.on_message, 60000.0)

    # We should now still have 5 buy orders, but at a higher price. The other
    # orders should be canceled.
    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        (59405.9, 58817.7, 58235.3, 57658.7, 57087.8),
        (0.00168333, 0.00170016, 0.00171717, 0.00173434, 0.00175168),
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.side == "buy"
        assert order.price == price
        assert order.volume == volume

    # ==========================================================================
    # 3. FILLING A BUY ORDER
    # Now lets let the price drop a bit so that a buy order gets triggered.
    await instance.trade.on_ticker_update(instance.on_message, 59900.0)

    # Quick re-check ... the price update should not affect any orderbook
    # changes when dropping.
    current_orders = instance.orderbook.get_orders().all()
    for order, price, volume, side in zip(
        current_orders,
        (59405.9, 58817.7, 58235.3, 57658.7, 57087.8),
        (0.00168333, 0.00170016, 0.00171717, 0.00173434, 0.00175168),
        ["buy"] * 5,
        strict=False,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.side == side
        assert order.volume == volume

    assert instance.orderbook.count() == 5

    await instance.trade.on_ticker_update(instance.on_message, 59000.0)
    # Ensure that we have 4 buy orders and 1 sell order
    for order, price, volume, side in zip(
        instance.orderbook.get_orders().all(),
        [58817.7, 58235.3, 57658.7, 57087.8, 59999.9],
        [0.00170016, 0.00171717, 0.00173434, 0.00175168, 0.00168333],
        ["buy"] * 4 + ["sell"],
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.volume == volume
        assert order.side == side

    # ==========================================================================
    # 4. ENSURING N OPEN BUY ORDERS
    # If there is a new price event, the algorithm will place the 5th buy order.
    await instance.trade.on_ticker_update(instance.on_message, 59100.0)

    for order, price, volume, side in zip(
        instance.orderbook.get_orders().all(),
        (58817.7, 58235.3, 57658.7, 57087.8, 59999.9, 56522.5),
        (0.00170016, 0.00171717, 0.00173434, 0.00175168, 0.00168333, 0.0017692),
        ["buy"] * 4 + ["sell"] + ["buy"],
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.volume == volume
        assert order.side == side

    # ==========================================================================
    # 5. FILLING A SELL ORDER
    # Now let's see if the sell order gets triggered.
    await instance.trade.on_ticker_update(instance.on_message, 60000.0)
    assert instance.ticker.last == 60000.0

    for order, price, volume, side in zip(
        instance.orderbook.get_orders().all(),
        (58817.7, 58235.3, 57658.7, 57087.8, 56522.5),
        (0.00170016, 0.00171717, 0.00173434, 0.00175168, 0.0017692),
        ["buy"] * 5,
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.volume == volume
        assert order.side == side

    # ... as we can see, the sell order got removed from the orderbook.
    # ... there is no new corresponding buy order placed - this would only be
    # the case for the case, if there would be more sell orders.
    # As usual, if the price would rise higher, the buy orders would shift up.

    # ==========================================================================
    # 6. RAPID PRICE DROP - FILLING ALL BUY ORDERS
    # Now check the behavior for a rapid price drop.
    await instance.trade.on_ticker_update(instance.on_message, 50000.0)
    assert instance.ticker.last == 50000.0

    for order, price, volume in zip(
        instance.orderbook.get_orders().all(),
        (59405.8, 58817.6, 58235.2, 57658.6, 57087.7),
        (0.00170016, 0.00171717, 0.00173434, 0.00175168, 0.0017692),
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.side == "sell"
        assert order.price == price
        assert order.volume == volume

    # ==========================================================================
    # 7. ENSURE N OPEN BUY ORDERS
    await instance.trade.on_ticker_update(instance.on_message, 59100.0)
    current_orders = instance.orderbook.get_orders().all()
    assert len(current_orders) == 6

    for order, price, volume in zip(
        (o for o in current_orders if o.side == "sell"),
        (59405.8,),
        (0.00170016,),
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.volume == volume
        assert order.side == "sell"

    for order, price, volume in zip(
        (o for o in current_orders if o.side == "buy"),
        (58514.8, 57935.4, 57361.7, 56793.7, 56231.3),
        (0.00170896, 0.00172606, 0.00174332, 0.00176075, 0.00177836),
        strict=True,
    ):
        assert order.userref == instance.userref
        assert order.symbol == "BTCUSD"
        assert order.price == price
        assert order.volume == volume
        assert order.side == "buy"

    assert instance.orderbook.count() == 6

    # ==========================================================================
    # 8. MAX INVESTMENT REACHED

    # First ensure that new buy orders can be placed...
    assert not instance.max_investment_reached
    instance.om.cancel_all_open_buy_orders()
    assert instance.orderbook.count() == 1
    await instance.trade.on_ticker_update(instance.on_message, 50000.0)
    assert instance.orderbook.count() == 6

    # Now with a different max investment, the max investment should be reached
    # and no further orders be placed.
    assert not instance.max_investment_reached
    instance.max_investment = 202  # 200 USD + fee
    instance.om.cancel_all_open_buy_orders()
    assert instance.orderbook.count() == 1
    await instance.trade.on_ticker_update(instance.on_message, 50000.0)
    assert instance.orderbook.count() == 2
    assert instance.max_investment_reached


@pytest.mark.integration
@pytest.mark.asyncio
@mock.patch("kraken_infinity_grid.order_management.sleep", return_value=None)
@mock.patch("kraken_infinity_grid.gridbot.sleep", return_value=None)
async def test_integration_GridSell_unfilled_surplus(
    mock_sleep_gridbot: mock.Mock,  # noqa: ARG001
    mock_sleep_order_management: mock.Mock,  # noqa: ARG001
    instance: KrakenInfinityGridBot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Integration test for the GridSell strategy using pre-generated websocket
    messages.

    This test checks if the unfilled surplus is handled correctly.

    unfilled surplus: The base currency volume that was partly filled by an buy
    order, before the order was cancelled.
    """
    caplog.set_level(logging.INFO)

    # Mock the initial setup
    instance.market.get_ticker.return_value = {"XXBTZUSD": {"c": ["50000.0"]}}

    await instance.trade.on_ticker_update(instance.on_message, 50000.0)
    assert not instance.state_machine.facts["ready_to_trade"]

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
    assert instance.state_machine.facts["ready_to_trade"]

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
        (49504.9, 49014.7, 48529.4, 48048.9, 47573.1),
        (0.00202, 0.0020402, 0.0020606, 0.00208121, 0.00210202),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == "buy"
        assert order.symbol == "BTCUSD"
        assert order.userref == instance.userref

    # ==========================================================================
    # 2. BUYING PARTLY FILLED and ensure that the unfilled surplus is handled
    instance.trade.fill_order(instance.orderbook.get_orders().first().txid, 0.002)
    assert instance.orderbook.count() == 5

    balances = instance.trade.get_balances()
    assert balances["XXBT"]["balance"] == "100.002"
    assert float(balances["ZUSD"]["balance"]) == pytest.approx(999400.99)

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
    assert len(instance.trade.get_open_orders()["open"]) == 5

    order = next(o for o in instance.orderbook.get_orders().all() if o.price == 49504.9)
    instance.trade.fill_order(order["txid"], 0.002)
    instance.om.handle_cancel_order(order["txid"])

    assert len(instance.trade.get_open_orders()["open"]) == 5
    assert instance.configuration.get()["vol_of_unfilled_remaining"] == 0.0

    sell_orders = instance.orderbook.get_orders(filters={"side": "sell"}).all()
    assert sell_orders[0].price == 50500.0
    assert sell_orders[0].volume == pytest.approx(0.00199014)
