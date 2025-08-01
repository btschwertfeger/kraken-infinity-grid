# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#


from typing import Self
from unittest import mock
from unittest.mock import Mock, patch

import pytest

from kraken_infinity_grid.strategies.c_dca import CDCAStrategy
from kraken_infinity_grid.strategies.grid_base import GridStrategyBase
from kraken_infinity_grid.strategies.grid_hodl import GridHODLStrategy
from kraken_infinity_grid.strategies.grid_sell import GridSellStrategy
from kraken_infinity_grid.strategies.swing import SwingStrategy


class TestGridBase:

    @pytest.fixture(
        params=[
            CDCAStrategy,
            GridHODLStrategy,
            GridSellStrategy,
            GridStrategyBase,
            SwingStrategy,
        ],
    )
    def strategy_class(self, request):
        """Parametrized fixture providing different strategy classes."""
        return request.param

    @pytest.fixture
    def mock_strategy(
        self: Self,
        strategy_class,
        mock_config: mock.MagicMock,
        mock_dependencies: mock.MagicMock,
    ):
        """Create a Strategy instance with mocked dependencies."""
        with (
            patch("kraken_infinity_grid.strategies.grid_base.Orderbook"),
            patch("kraken_infinity_grid.strategies.grid_base.Configuration"),
            patch("kraken_infinity_grid.strategies.grid_base.PendingTXIDs"),
            patch("kraken_infinity_grid.strategies.grid_base.UnsoldBuyOrderTXIDs"),
        ):
            strategy = strategy_class(
                config=mock_config,
                event_bus=mock_dependencies["event_bus"],
                state_machine=mock_dependencies["state_machine"],
                db=mock_dependencies["db"],
            )

            strategy._configuration_table = Mock()
            strategy._configuration_table.get.return_value = {
                "price_of_highest_buy": 100.0,
            }
            strategy._orderbook_table = Mock()
            strategy._ticker = 50000.0

            return strategy

    def test_get_buy_order_price_normal_case(
        self: Self,
        mock_strategy,
    ) -> None:
        """Test buy order price calculation for normal market conditions."""
        last_price = 50000.0
        expected_price = 47619.047619047619
        result = mock_strategy._get_buy_order_price(last_price)

        assert result == pytest.approx(expected_price, rel=1e-4)
        assert result < last_price  # Buy order should be below market price

    def test_get_buy_order_price_above_ticker(
        self: Self,
        mock_strategy,
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
        strategy_class,
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
                strategy = strategy_class(
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
