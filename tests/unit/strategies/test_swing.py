# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

"""Unit tests for the Swing Strategy class."""

from typing import Self
from unittest import mock
from unittest.mock import Mock, patch

import pytest

from kraken_infinity_grid.strategies.swing import SwingStrategy


class TestSwingStrategy:
    """Test cases for SwingStrategy order price calculation methods."""

    @pytest.fixture
    def mock_strategy(
        self: Self,
        mock_config: mock.MagicMock,
        mock_dependencies: mock.MagicMock,
    ) -> SwingStrategy:
        """Create a Swing Strategy instance with mocked dependencies."""
        with (
            patch("kraken_infinity_grid.strategies.grid_base.Orderbook"),
            patch("kraken_infinity_grid.strategies.grid_base.Configuration"),
            patch("kraken_infinity_grid.strategies.grid_base.PendingTXIDs"),
            patch("kraken_infinity_grid.strategies.grid_base.UnsoldBuyOrderTXIDs"),
        ):
            strategy = SwingStrategy(
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

    def test_get_sell_order_price_normal_case(
        self: Self,
        mock_strategy: SwingStrategy,
    ) -> None:
        """Test sell order price calculation for normal market conditions."""
        last_price = 50000.0
        expected_price = 52500.0  # 50000 * (1 + interval)
        result = mock_strategy._get_sell_order_price(last_price)

        assert result == pytest.approx(expected_price, rel=1e-4)
        assert result > last_price  # Sell order should be above market price

    def test_get_sell_order_price_below_ticker(
        self: Self,
        mock_strategy: SwingStrategy,
    ) -> None:
        """Test sell order price calculation when calculated price is below ticker."""
        # Set a low last_price that would make the calculated order_price < ticker
        last_price = 40000.0  # Lower than ticker (50000.0)
        expected_price = 52500.0  # ticker * (1 + interval)

        result = mock_strategy._get_sell_order_price(last_price)
        assert result == pytest.approx(expected_price, rel=1e-4)
        assert result > mock_strategy._ticker

    def test_get_sell_order_price_updates_highest_buy_price(
        self: Self,
        mock_strategy: SwingStrategy,
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
        mock_strategy: SwingStrategy,
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

    def test_get_sell_order_price_extra_sell_normal_case(
        self: Self,
        mock_strategy: SwingStrategy,
    ) -> None:
        """Test extra sell order price calculation for normal market conditions."""
        last_price = 50000.0
        # Extra sell: last_price * (1 + interval) * (1 + interval)
        expected_price = 55125.0  # 50000 * (1 + 0.05) * (1 + 0.05)
        result = mock_strategy._get_sell_order_price(last_price, extra_sell=True)

        assert result == pytest.approx(expected_price, rel=1e-4)
        assert result > last_price

    def test_get_sell_order_price_extra_sell_below_highest_buy(
        self: Self,
        mock_strategy: SwingStrategy,
    ) -> None:
        """Test extra sell order when calculated price is below highest buy price."""
        # Set high highest buy price
        mock_strategy._configuration_table.get.return_value = {
            "price_of_highest_buy": 60000.0,
        }
        last_price = 50000.0
        # Should use highest buy price instead: 60000 * (1 + 0.05) * (1 + 0.05)
        expected_price = 66150.0

        result = mock_strategy._get_sell_order_price(last_price, extra_sell=True)

        assert result == pytest.approx(expected_price, rel=1e-4)
        assert result > last_price

    def test_check_extra_sell_order_no_sell_orders(
        self: Self,
        mock_strategy: SwingStrategy,
    ) -> None:
        """Test check_extra_sell_order when no sell orders exist."""
        # Mock the orderbook table to return 0 sell orders
        mock_strategy._orderbook_table.count.return_value = 0

        # Mock exchange domain
        mock_strategy._exchange_domain = Mock()
        mock_strategy._exchange_domain.SELL = "sell"

        # Mock rest API and balances
        mock_strategy._rest_api = Mock()
        mock_balances = Mock()
        mock_balances.base_available = 2.0  # Enough balance
        mock_strategy._rest_api.get_pair_balance.return_value = mock_balances

        # Mock other required attributes
        mock_strategy._amount_per_grid_plus_fee = 100.0
        mock_strategy._config = Mock()
        mock_strategy._config.base_currency = "BTC"
        mock_strategy._config.quote_currency = "USD"
        mock_strategy._config.name = "TestBot"

        # Mock event bus
        mock_strategy._event_bus = Mock()

        # Mock handle_arbitrage method
        mock_strategy._handle_arbitrage = Mock()

        mock_strategy._check_extra_sell_order()

        # Should call handle_arbitrage to place extra sell order
        mock_strategy._handle_arbitrage.assert_called_once()

    def test_check_extra_sell_order_with_existing_sell_orders(
        self: Self,
        mock_strategy: SwingStrategy,
    ) -> None:
        """Test check_extra_sell_order when sell orders already exist."""
        # Mock the orderbook table to return 1 sell order
        mock_strategy._orderbook_table.count.return_value = 1

        # Mock exchange domain
        mock_strategy._exchange_domain = Mock()
        mock_strategy._exchange_domain.SELL = "sell"

        # Mock handle_arbitrage method
        mock_strategy._handle_arbitrage = Mock()

        mock_strategy._check_extra_sell_order()

        # Should not call handle_arbitrage
        mock_strategy._handle_arbitrage.assert_not_called()

    def test_check_extra_sell_order_insufficient_balance(
        self: Self,
        mock_strategy: SwingStrategy,
    ) -> None:
        """Test check_extra_sell_order when insufficient balance exists."""
        # Mock the orderbook table to return 0 sell orders
        mock_strategy._orderbook_table.count.return_value = 0

        # Mock exchange domain
        mock_strategy._exchange_domain = Mock()
        mock_strategy._exchange_domain.SELL = "sell"

        # Mock rest API and balances (insufficient balance)
        mock_strategy._rest_api = Mock()
        mock_balances = Mock()
        mock_balances.base_available = 0.001  # Insufficient balance
        mock_strategy._rest_api.get_pair_balance.return_value = mock_balances

        # Mock other required attributes
        mock_strategy._amount_per_grid_plus_fee = 100.0
        mock_strategy._config = Mock()
        mock_strategy._config.base_currency = "BTC"
        mock_strategy._config.quote_currency = "USD"

        # Mock handle_arbitrage method
        mock_strategy._handle_arbitrage = Mock()

        mock_strategy._check_extra_sell_order()

        # Should not call handle_arbitrage due to insufficient balance
        mock_strategy._handle_arbitrage.assert_not_called()

    def test_new_sell_order_dry_run(self: Self, mock_strategy: SwingStrategy) -> None:
        """Test new_sell_order method in dry run mode."""
        mock_strategy._config.dry_run = True
        mock_strategy._new_sell_order(50000.0)

        # Should not interact with orderbook table
        mock_strategy._orderbook_table.remove.assert_not_called()

    def test_new_sell_order_with_txid_to_delete(
        self: Self,
        mock_strategy: SwingStrategy,
    ) -> None:
        """Test new_sell_order method with transaction ID to delete."""
        txid_to_delete = "test_txid_123"

        # Mock the unsold buy order txids table
        mock_strategy._unsold_buy_order_txids_table = Mock()
        mock_strategy._unsold_buy_order_txids_table.get.return_value.first.return_value = (
            None
        )

        # Mock the rest API for order retrieval
        mock_strategy._rest_api = Mock()
        mock_order = Mock()
        mock_order.status = "closed"
        mock_order.vol_exec = 0.001
        mock_strategy._rest_api.get_order_with_retry.return_value = mock_order
        mock_strategy._rest_api.truncate.side_effect = (
            lambda amount, **kwargs: amount  # noqa: ARG005
        )
        mock_strategy._rest_api.get_pair_balance.return_value.base_available = 1.0
        mock_strategy._rest_api.create_order.return_value.txid = "new_sell_order_txid"

        # Mock exchange domain
        mock_strategy._exchange_domain = Mock()
        mock_strategy._exchange_domain.CLOSED = "closed"
        mock_strategy._exchange_domain.SELL = "sell"

        # Mock pending txids table
        mock_strategy._pending_txids_table = Mock()

        # Mock assign order method
        mock_strategy._assign_order_by_txid = Mock()

        mock_strategy._new_sell_order(50000.0, txid_to_delete=txid_to_delete)

        # Should remove the specified transaction ID from orderbook
        mock_strategy._orderbook_table.remove.assert_called_once_with(
            filters={"txid": txid_to_delete},
        )
