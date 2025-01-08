#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Unit tests for the KrakenInfinityGridBot class."""

import logging
from unittest import mock

import pytest
import pytest_asyncio
from kraken.spot import Market, Trade, User

from kraken_infinity_grid.database import Configuration, Orderbook, UnsoldBuyOrderTXIDs
from kraken_infinity_grid.gridbot import KrakenInfinityGridBot
from kraken_infinity_grid.order_management import OrderManager
from kraken_infinity_grid.setup import SetupManager
from kraken_infinity_grid.telegram import Telegram


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


@pytest_asyncio.fixture
async def instance(
    config: dict,
    db_config: dict,
) -> KrakenInfinityGridBot:
    """Fixture to create a KrakenInfinityGridBot instance for testing."""
    instance = KrakenInfinityGridBot(
        key="key",
        secret="secret",
        config=config,
        db_config=db_config,
    )
    instance.user = mock.MagicMock(spec=User)
    instance.market = mock.MagicMock(spec=Market)
    instance.trade = mock.MagicMock(spec=Trade)
    instance.orderbook = mock.MagicMock(spec=Orderbook)
    instance.configuration = mock.MagicMock(spec=Configuration)
    instance.ticker = mock.MagicMock()
    instance.telegram = mock.MagicMock(spec=Telegram)
    instance.sm = mock.MagicMock(spec=SetupManager)
    instance.om = mock.MagicMock(spec=OrderManager)
    instance.unsold_buy_order_txids = mock.Mock(spec=UnsoldBuyOrderTXIDs)
    yield instance
    await instance.async_close()
    await instance.stop()


# ==============================================================================


def test_get_balances(instance: KrakenInfinityGridBot) -> None:
    """Test the get_balances method."""

    instance.user.get_balances.return_value = {
        "XXBT": {"balance": "1.0", "hold_trade": "0.1"},
        "ZEUR": {"balance": "1000.0", "hold_trade": "100.0"},
    }
    instance.zbase_currency = "XXBT"
    instance.xquote_currency = "ZEUR"
    balances = instance.get_balances()
    assert balances["base_balance"] == 1.0
    assert balances["quote_balance"] == 1000.0
    assert balances["base_available"] == 0.9
    assert balances["quote_available"] == 900.0


@mock.patch(
    "kraken_infinity_grid.gridbot.KrakenInfinityGridBot.get_active_buy_orders",
    return_value=[{"price": 50000.0, "vol": 0.1}, {"price": 49000.0, "vol": 0.2}],
)
def test_get_current_buy_prices(
    mock_get_active_buy_orders: mock.Mock,  # noqa: ARG001
    instance: KrakenInfinityGridBot,
) -> None:
    """Test the get_current_buy_prices method."""

    instance.get_active_buy_orders.return_value = [
        {"price": 50000.0},
        {"price": 49000.0},
    ]
    assert instance.get_current_buy_prices() == [50000.0, 49000.0]


def test_get_active_buy_orders(instance: KrakenInfinityGridBot) -> None:
    """Test the get_active_buy_orders method."""
    instance.orderbook.get_orders.return_value = [
        {"txid": "txid1", "side": "buy"},
        {"txid": "txid2", "side": "buy"},
    ]
    orders = instance.get_active_buy_orders()
    assert len(orders) == 2
    assert orders[0]["txid"] == "txid1"
    assert orders[1]["txid"] == "txid2"


def test_get_active_sell_orders(instance: KrakenInfinityGridBot) -> None:
    """Test the get_active_sell_orders method."""
    instance.orderbook.get_orders.return_value = [
        {"txid": "txid1", "side": "sell"},
        {"txid": "txid2", "side": "sell"},
    ]
    orders = instance.get_active_sell_orders()
    assert len(orders) == 2
    assert orders[0]["txid"] == "txid1"
    assert orders[1]["txid"] == "txid2"


def test_get_order_price_sell(instance: KrakenInfinityGridBot) -> None:
    """Test the get_order_price method for sell orders."""
    instance.strategy = "GridSell"
    instance.interval = 0.01
    instance.ticker.last = 50000.0
    instance.configuration.get.return_value = {"price_of_highest_buy": 50000.0}

    # Test regular sell order: ticker.last > order_price
    price = instance.get_order_price(side="sell", last_price=49000.0)
    assert price == 50500.0

    # Test regular sell order: ticker.last <= order_price
    price = instance.get_order_price(side="sell", last_price=51000.0)
    assert price == 51510.0

    instance.strategy = "SWING"

    # Test extra sell order for SWING: order_price >= price_of_highest_buy
    price = instance.get_order_price(side="sell", last_price=51000.0, extra_sell=True)
    assert price == 52025.1

    # Test extra sell order for SWING: order_price < price_of_highest_buy
    price = instance.get_order_price(side="sell", last_price=49000.0, extra_sell=True)
    assert price == 51005.0


def test_get_order_price_buy(instance: KrakenInfinityGridBot) -> None:
    """
    Test the get_order_price method for buy orders.

    This is essential for calculating the price of the next buy order.
    """
    instance.interval = 0.01
    instance.ticker.last = 50000.0

    # Test regular buy order: order_price > ticker.last
    price = instance.get_order_price(side="buy", last_price=51000.0)
    assert price == pytest.approx(49504.95049504)

    # Test buy order with lower last price
    price = instance.get_order_price(side="buy", last_price=49000.0)
    assert price == pytest.approx(48514.851485148514)


def test_get_order_price_invalid_side(instance: KrakenInfinityGridBot) -> None:
    """Test the get_order_price method with an invalid side."""
    with pytest.raises(ValueError, match=r".*Unknown side.*"):
        instance.get_order_price(side="invalid", last_price=50000.0)


def test_get_value_of_orders(instance: KrakenInfinityGridBot) -> None:
    """Test the get_value_of_orders method."""
    orders = [
        {"price": 50000.0, "volume": 0.1},
        {"price": 49000.0, "volume": 0.2},
    ]
    value = instance.get_value_of_orders(orders)
    assert value == 14800.0

    value = instance.get_value_of_orders([])
    assert value == 0


def test_investment(instance: KrakenInfinityGridBot) -> None:
    """Test the investment property."""
    instance.orderbook.get_orders.return_value = [
        {"price": 50000.0, "volume": 0.1},
        {"price": 49000.0, "volume": 0.2},
    ]
    assert instance.investment == 14800.0

    instance.orderbook.get_orders.return_value = []
    assert instance.investment == 0.0


def test_max_investment_reached(instance: KrakenInfinityGridBot) -> None:
    """Test the max_investment_reached property."""
    instance.amount_per_grid = 1000.0
    instance.fee = 0.01
    instance.max_investment = 20000.0

    # Case where max investment is not reached
    instance.orderbook.get_orders.return_value = [
        {"price": 50000.0, "volume": 0.1},
        {"price": 49000.0, "volume": 0.2},
    ]
    assert not instance.max_investment_reached

    # Case where max investment is reached
    instance.orderbook.get_orders.return_value = [
        {"price": 50000.0, "volume": 0.3},
        {"price": 49000.0, "volume": 0.2},
    ]
    assert instance.max_investment_reached


# ==============================================================================
# on_message
##
@pytest.mark.asyncio
async def test_on_message(
    instance: KrakenInfinityGridBot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the on_message method."""
    caplog.set_level(logging.INFO)

    await instance.on_message(["not a dict"])
    assert "Message is not a dict" in caplog.text

    # Just check that they run through....
    await instance.on_message({"channel": "heartbeat"})
    await instance.on_message({"channel": "pong"})
    await instance.on_message({"channel": "status"})
    await instance.on_message({"method": "subscribe", "success": True})

    # Test ticker channel
    assert not instance._KrakenInfinityGridBot__ticker_channel_connected
    await instance.on_message({"channel": "ticker", "data": {"last": 50000.0}})
    assert instance._KrakenInfinityGridBot__ticker_channel_connected

    # Ensure setup did not run yet
    instance.sm.prepare_for_trading.assert_not_called()
    assert not instance.is_ready_to_trade

    # Ensure that even if the bot is receiving ticker messages, it will not
    # start any trading actions. For the trades, we can ensure this by checking
    # if the configuration table was updated due to a new price update, where we
    # always save the time of the last price update.
    await instance.on_message({"channel": "ticker", "data": {"last": 50000.0}})
    instance.configuration.update.assert_not_called()

    instance.sm.prepare_for_trading.assert_not_called()

    # We also need to ensure that the execution channel messages won't trigger
    # any actions. Even though it is not connected so far, we can simulate it.
    # Test executions channel
    assert not instance._KrakenInfinityGridBot__execution_channel_connected
    await instance.on_message(
        {
            "channel": "executions",
            "data": [{"exec_type": "new"}],
        },
    )
    assert instance._KrakenInfinityGridBot__execution_channel_connected

    # Ensure that the algorithm initiated preparation for trading
    instance.sm.prepare_for_trading.assert_called_once()


@pytest.mark.asyncio
async def test_on_message_failing_subscribe(
    instance: KrakenInfinityGridBot,
) -> None:
    """Test the on_message method failing in case subscribing fails."""
    with pytest.raises(SystemExit):
        await instance.on_message({"method": "subscribe", "success": False})


@pytest.mark.asyncio
async def test_on_message_ticker(instance: KrakenInfinityGridBot) -> None:
    """Test the on_message method and ticker behavior."""

    assert not instance._KrakenInfinityGridBot__ticker_channel_connected
    await instance.on_message({"channel": "ticker", "data": {"last": 50000.0}})
    assert instance._KrakenInfinityGridBot__ticker_channel_connected

    # Just verify that ...
    instance.sm.prepare_for_trading.assert_not_called()

    # Set readiness by hand
    instance.is_ready_to_trade = True
    instance.ticker.last = 50000.0

    instance.om.check_price_range.assert_not_called()
    # Send a new ticker message
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [
                {
                    "symbol": "BTC/USD",
                    "last": 50000.0,
                },
            ],
        },
    )
    # == Ensure not checking price range if price does not change
    instance.om.check_price_range.assert_not_called()

    # == Ensure saving the last price time
    instance.configuration.update.assert_called_once()
    assert instance.ticker.last == 50000.0

    # == Ensure doing nothing if the price did not change
    instance.om.check_price_range.assert_not_called()

    # == Simulate a finished buy order which was missed to sell
    instance.unsold_buy_order_txids.count.return_value = 1
    instance.om.add_missed_sell_orders.assert_not_called()

    # Trigger another price update
    await instance.on_message(
        {
            "channel": "ticker",
            "data": [
                {
                    "symbol": "BTC/USD",
                    "last": 51000.0,
                },
            ],
        },
    )
    # == Ensure missed sell orders will be handled in case there are any
    instance.om.add_missed_sell_orders.assert_called_once()

    # == Ensure price range check is performed on new price
    instance.om.check_price_range.assert_called_once()


@pytest.mark.asyncio
async def test_on_message_executions(instance: KrakenInfinityGridBot) -> None:
    """Test the on_message method and execution behavior."""

    assert not instance._KrakenInfinityGridBot__execution_channel_connected
    await instance.on_message(
        {
            "channel": "executions",
            "data": [{"exec_type": "new"}],
        },
    )
    assert instance._KrakenInfinityGridBot__execution_channel_connected

    # Just verify that ...
    instance.sm.prepare_for_trading.assert_not_called()
    instance.om.check_price_range.assert_not_called()

    # Set readiness by hand
    instance.is_ready_to_trade = True

    # Ignore snapshots
    await instance.on_message(
        {"channel": "executions", "type": "snapshot", "data": []},
    )

    # == Send a new execution message for new orders
    await instance.on_message(
        {
            "channel": "executions",
            "type": "update",
            "data": [{"exec_type": "new", "order_id": "txid1"}],
        },
    )
    instance.om.assign_order_by_txid.assert_called_once_with("txid1")

    # == Send a new execution message for filled orders
    await instance.on_message(
        {
            "channel": "executions",
            "type": "update",
            "data": [{"exec_type": "filled", "order_id": "txid1"}],
        },
    )
    instance.om.handle_filled_order_event.assert_called_once_with("txid1")

    # == Send a new execution message for canceled or expired orders
    await instance.on_message(
        {
            "channel": "executions",
            "type": "update",
            "data": [{"exec_type": "canceled", "order_id": "txid1"}],
        },
    )
    instance.orderbook.remove.assert_called_once_with(filters={"txid": "txid1"})
