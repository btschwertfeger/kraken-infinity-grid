#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from kraken_infinity_grid.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ==============================================================================


def test_cli_help(runner: CliRunner) -> None:
    """Test the help message"""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_cli_version(runner: CliRunner) -> None:
    """Test the version message"""
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0


@patch.dict(os.environ, {})
@patch("kraken_infinity_grid.gridbot.KrakenInfinityGridBot")
def test_cli_run(mock_bot: MagicMock, runner: CliRunner) -> None:
    """Test the run command"""
    command = [
        "--api-key",
        "test_api_key",
        "--secret-key",
        "test_secret_key",
        "run",
        "--name",
        "test_bot",
        "--base-currency",
        "BTC",
        "--quote-currency",
        "USD",
        "--amount-per-grid",
        "100",
        "--interval",
        "0.04",
        "--n-open-buy-orders",
        "3",
        "--userref",
        "123456",
        "--db-user",
        "test_db_user",
        "--db-password",
        "test_db_password",
        "--db-name",
        "test_db_name",
        "--db-host",
        "test_db_host",
        "--db-port",
        "5432",
        "--strategy",
        "DCA",
    ]
    mock_bot.return_value.run = AsyncMock()
    result = runner.invoke(cli, command)

    assert result.exit_code == 0
    mock_bot.assert_called_once()
    mock_bot.return_value.run.assert_any_await()


@patch.dict(os.environ, {})
@patch("kraken.spot.Trade")
def test_cli_cancel(mock_trade: MagicMock, runner: CliRunner) -> None:
    """Test the cancel command"""
    command = [
        "--api-key",
        "test_api_key",
        "--secret-key",
        "test_secret_key",
        "cancel",
        "--force",
    ]
    result = runner.invoke(cli, command)
    assert result.exit_code == 0
    mock_trade.return_value.cancel_all_orders.assert_called_once()
