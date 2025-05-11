# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

import os
from pathlib import Path
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
def test_cli_run(mock_bot: MagicMock, runner: CliRunner, sqlite_file: Path) -> None:
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
        "--sqlite-file",
        sqlite_file,
        "--strategy",
        "cDCA",
    ]
    mock_bot.return_value.run = AsyncMock()
    result = runner.invoke(cli, command)

    assert result.exit_code == 0
    mock_bot.assert_called_once()
    mock_bot.return_value.run.assert_any_await()
