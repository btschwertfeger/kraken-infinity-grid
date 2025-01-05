#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Unit tests for the Telegram class."""

import logging
from unittest import mock

import pytest

from kraken_infinity_grid.telegram import Telegram


@pytest.fixture
def telegram() -> Telegram:
    """Fixture to create a Telegram instance for testing."""
    strategy = mock.Mock()
    telegram_token = "test_token"  # noqa: S105
    telegram_chat_id = "test_chat_id"
    exception_token = "exception_token"  # noqa: S105
    exception_chat_id = "exception_chat_id"
    return Telegram(
        strategy,
        telegram_token,
        telegram_chat_id,
        exception_token,
        exception_chat_id,
    )


@mock.patch("kraken_infinity_grid.telegram.requests.post")
def test_send_to_telegram(
    mock_post: mock.Mock,
    telegram: Telegram,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    """Test sending a regular message to Telegram."""
    mock_post.return_value.status_code = 200
    telegram.send_to_telegram("Test message")
    mock_post.assert_called_once_with(
        url=f"https://api.telegram.org/bot{telegram._Telegram__telegram_token}/sendMessage",
        params={
            "chat_id": telegram._Telegram__telegram_chat_id,
            "text": "Test message",
            "parse_mode": "markdown",
        },
        timeout=10,
    )
    assert "Test message" in caplog.text


@mock.patch("kraken_infinity_grid.telegram.requests.post")
def test_send_to_telegram_exception(
    mock_post: mock.Mock,
    telegram: Telegram,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test sending an exception message to Telegram."""
    mock_post.return_value.status_code = 200
    telegram.send_to_telegram("Exception message", exception=True)
    mock_post.assert_called_once_with(
        url=f"https://api.telegram.org/bot{telegram._Telegram__exception_token}/sendMessage",
        params={
            "chat_id": telegram._Telegram__exception_chat_id,
            "text": "```\nException message\n```",
            "parse_mode": "markdown",
        },
        timeout=10,
    )
    assert "Exception message" in caplog.text


@mock.patch("kraken_infinity_grid.telegram.requests.post")
def test_send_to_telegram_failure(
    mock_post: mock.Mock,
    telegram: Telegram,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test handling of a failed message send to Telegram."""
    mock_post.return_value.status_code = 400
    telegram.send_to_telegram("Test message")
    assert "Failed to send message to Telegram" in caplog.text


@mock.patch("kraken_infinity_grid.telegram.Telegram.send_to_telegram")
def test_send_bot_update(
    mock_send_to_telegram: mock.Mock,
    telegram: Telegram,
) -> None:
    """Test sending a bot status update to Telegram."""
    telegram._Telegram__s.get_balances.return_value = {
        "base_balance": 1.0,
        "quote_balance": 100.0,
        "quote_available": 50.0,
        "base_available": 0.5,
    }
    telegram._Telegram__s.symbol = "BTC/USD"
    telegram._Telegram__s.ticker.last = 50000.0
    telegram._Telegram__s.quote_currency = "USD"
    telegram._Telegram__s.base_currency = "BTC"
    telegram._Telegram__s.configuration.get.return_value = {
        "vol_of_unfilled_remaining": 0.1,
    }
    telegram._Telegram__s.investment = 1000.0
    telegram._Telegram__s.max_investment = 2000.0
    telegram._Telegram__s.amount_per_grid = 10.0
    telegram._Telegram__s.cost_decimals = 5
    telegram._Telegram__s.orderbook.count.return_value = 5
    telegram._Telegram__s.orderbook.get_orders.return_value = [
        {"side": "buy", "price": 49000.0},
        {"side": "sell", "price": 51000.0},
    ]

    telegram.send_bot_update()
    assert mock_send_to_telegram.called

    # Check parts of the message format. This is not a beauty but ok for now.
    message = mock_send_to_telegram.call_args[0][0]
    assert "👑 BTC/USD" in message
    assert "└ Price » 50000.0 USD" in message
    assert "⚜️ Account" in message
    assert "├ Total BTC » 1.0" in message
    assert "├ Total USD » 100.0" in message
    assert "├ Available USD » 50.0" in message
    assert "├ Available BTC » 0.4" in message
    assert "├ Unfilled surplus of BTC » 0.1" in message
    assert "├ Bot-managed wealth » 50100.0 USD" in message
    assert "└ Investment » 1000.0 / 2000.0 USD" in message
    assert "💠 Orders" in message
    assert "├ Amount per Grid » 10.0 USD" in message
    assert "└ Open orders » 5" in message
    assert "🏷️ Price in USD" in message
    assert " │  ┌[ 51000.0 (+2.00%)" in message
    assert " └──┼> 50000.0" in message
    assert "    └[ 49000.0 (-2.00%)" in message
