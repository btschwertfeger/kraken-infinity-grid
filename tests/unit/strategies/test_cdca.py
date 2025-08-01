# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

"""Unit tests for the cDCA Strategy class."""

from typing import Self
from unittest import mock
from unittest.mock import Mock, patch

import pytest

from kraken_infinity_grid.models.configuration import BotConfigDTO
from kraken_infinity_grid.strategies.c_dca import CDCAStrategy


class TestCDCAStrategy:
    """Test cases for CDCAStrategy order price calculation methods."""

    @pytest.fixture
    def mock_config(self: Self) -> BotConfigDTO:
        """Create a mock configuration for testing."""
        config = Mock(spec=BotConfigDTO)
        config.interval = 0.05  # 5% interval
        config.dry_run = False
        config.userref = "123456"
        return config

    @pytest.fixture
    def mock_dependencies(self: Self) -> dict:
        """Create mock dependencies needed for cDCA Strategy initialization."""
        return {
            "event_bus": Mock(),
            "state_machine": Mock(),
            "db": Mock(),
        }

    @pytest.fixture
    def mock_strategy(
        self: Self,
        mock_config: mock.MagicMock,
        mock_dependencies: mock.MagicMock,
    ) -> CDCAStrategy:
        """Create a cDCA Strategy instance with mocked dependencies."""
        with (
            patch("kraken_infinity_grid.strategies.grid_base.Orderbook"),
            patch("kraken_infinity_grid.strategies.grid_base.Configuration"),
            patch("kraken_infinity_grid.strategies.grid_base.PendingTXIDs"),
            patch("kraken_infinity_grid.strategies.grid_base.UnsoldBuyOrderTXIDs"),
        ):
            strategy = CDCAStrategy(
                config=mock_config,
                event_bus=mock_dependencies["event_bus"],
                state_machine=mock_dependencies["state_machine"],
                db=mock_dependencies["db"],
            )

            # Mock the configuration table
            strategy._configuration_table = Mock()
            strategy._configuration_table.get.return_value = {
                "price_of_highest_buy": 100.0,
            }

            # Mock the orderbook table
            strategy._orderbook_table = Mock()

            # Set ticker value for testing
            strategy._ticker = 50000.0

            return strategy

    def test_get_buy_order_price_normal_case(
        self: Self,
        mock_strategy: mock.MagicMock,
    ) -> None:
        """Test buy order price calculation for normal market conditions."""
        last_price = 50000.0
        expected_price = 47619.047619047619
        result = mock_strategy._get_buy_order_price(last_price)

        assert result == pytest.approx(expected_price, rel=1e-4)
        assert result < last_price  # Buy order should be below market price

    def test_get_buy_order_price_above_ticker(
        self: Self,
        mock_strategy: mock.MagicMock,
    ) -> None:
        """Test buy order price calculation when calculated price exceeds ticker."""
        # Set a high last_price that would make the calculated order_price > ticker
        last_price = 60000.0  # Higher than ticker (50000.0)
        expected_price = 47619.047619047619

        result = mock_strategy._get_buy_order_price(last_price)
        assert result == pytest.approx(expected_price, rel=1e-4)
        assert result < mock_strategy._ticker

    def test_get_buy_order_price_different_intervals(
        self: Self,
        mock_config: mock.MagicMock,
        mock_dependencies: mock.MagicMock,
    ) -> None:
        """Test buy order price calculation with different interval values."""
        test_cases = [
            (0.01, 50000.0, 49504.9504950495),
            (0.10, 52000.0, 47272.72727272727),
            (0.20, 48000.0, 40000.0),
        ]

        for interval, last_price, expected_price in test_cases:
            mock_config.interval = interval

            with (
                patch("kraken_infinity_grid.strategies.grid_base.Orderbook"),
                patch("kraken_infinity_grid.strategies.grid_base.Configuration"),
                patch("kraken_infinity_grid.strategies.grid_base.PendingTXIDs"),
                patch("kraken_infinity_grid.strategies.grid_base.UnsoldBuyOrderTXIDs"),
            ):
                strategy = CDCAStrategy(
                    config=mock_config,
                    event_bus=mock_dependencies["event_bus"],
                    state_machine=mock_dependencies["state_machine"],
                    db=mock_dependencies["db"],
                )
                strategy._configuration_table = Mock()
                strategy._ticker = 50000.0

                result = strategy._get_buy_order_price(last_price)
                assert result == pytest.approx(expected_price, rel=1e-4)
                assert result < last_price

    def test_get_sell_order_price_returns_none(
        self: Self,
        mock_strategy: mock.MagicMock,
    ) -> None:
        """Test that sell order price always returns None for cDCA strategy."""
        last_price = 50000.0

        result = mock_strategy._get_sell_order_price(last_price)

        assert result is None

    def test_get_sell_order_price_updates_highest_buy_price(
        self: Self,
        mock_strategy: mock.MagicMock,
    ) -> None:
        """Test that sell order price method updates the highest buy price when appropriate."""
        # Set initial highest buy price lower than current price
        mock_strategy._configuration_table.get.return_value = {
            "price_of_highest_buy": 45000.0,
        }
        last_price = 50000.0

        mock_strategy._get_sell_order_price(last_price)

        # Should update the highest buy price
        mock_strategy._configuration_table.update.assert_called_once_with(
            {"price_of_highest_buy": last_price},
        )

    def test_get_sell_order_price_no_update_when_price_lower(
        self: Self,
        mock_strategy: mock.MagicMock,
    ) -> None:
        """Test that highest buy price is not updated when current price is lower."""
        # Set initial highest buy price higher than current price
        mock_strategy._configuration_table.get.return_value = {
            "price_of_highest_buy": 55000.0,
        }
        last_price = 50000.0

        mock_strategy._get_sell_order_price(last_price)

        # Should not update the highest buy price
        mock_strategy._configuration_table.update.assert_not_called()

    def test_check_extra_sell_order_does_nothing(
        self: Self,
        mock_strategy: mock.MagicMock,
    ) -> None:
        """Test that check_extra_sell_order method does nothing (no-op)."""
        # This method should not raise any exceptions and do nothing
        mock_strategy._check_extra_sell_order()

    def test_new_sell_order_dry_run(self: Self, mock_strategy: mock.MagicMock) -> None:
        """Test new_sell_order method in dry run mode."""
        mock_strategy._config.dry_run = True
        mock_strategy._new_sell_order(50000.0)

        # Should not interact with orderbook table
        mock_strategy._orderbook_table.remove.assert_not_called()

    def test_new_sell_order_with_txid_to_delete(
        self: Self,
        mock_strategy: mock.MagicMock,
    ) -> None:
        """Test new_sell_order method with transaction ID to delete."""
        txid_to_delete = "test_txid_123"

        mock_strategy._new_sell_order(50000.0, txid_to_delete=txid_to_delete)

        # Should remove the specified transaction ID
        mock_strategy._orderbook_table.remove.assert_called_once_with(
            filters={"txid": txid_to_delete},
        )
