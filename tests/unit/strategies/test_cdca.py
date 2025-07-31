# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

"""Unit tests for the CDCAStrategy class."""

from unittest.mock import MagicMock, patch

import pytest

from kraken_infinity_grid.strategies.c_dca import CDCAStrategy


class TestCDCAStrategy:
    """Test cases for CDCAStrategy."""

    @pytest.fixture
    def mock_strategy(self) -> CDCAStrategy:
        """Create a CDCAStrategy instance with mocked dependencies."""
        with (
            patch("kraken_infinity_grid.strategies.c_dca.GridStrategyBase.__init__"),
        ):
            strategy = CDCAStrategy.__new__(CDCAStrategy)

            # Mock the required attributes
            strategy._exchange_domain = MagicMock()
            strategy._exchange_domain.SELL = "sell"
            strategy._exchange_domain.BUY = "buy"

            strategy._config = MagicMock()
            strategy._config.interval = 0.02
            strategy._config.dry_run = False

            strategy._ticker = 50000.0
            strategy._orderbook_table = MagicMock()

            return strategy

    def test_get_order_price_sell_returns_none(
        self,
        mock_strategy: CDCAStrategy,
    ) -> None:
        """Test that sell orders return None for price."""
        result = mock_strategy._get_order_price("sell", 50000.0)

        assert result is None

    def test_get_order_price_buy_normal_case(self, mock_strategy: CDCAStrategy) -> None:
        """Test buy order price calculation for normal case."""
        last_price = 50000.0
        expected_price = 49019.60784313725

        result = mock_strategy._get_order_price("buy", last_price)

        assert result == pytest.approx(expected_price, rel=1e-5)

    def test_get_order_price_buy_price_exceeds_ticker(
        self,
        mock_strategy: CDCAStrategy,
    ) -> None:
        """Test buy order price when calculated price exceeds ticker."""
        mock_strategy._ticker = 45000.0
        last_price = 50000.0  # This would result in a price > ticker

        expected_price = 44117.647058823524

        result = mock_strategy._get_order_price("buy", last_price)

        assert result == pytest.approx(expected_price, rel=1e-5)

    def test_get_order_price_invalid_side_raises_error(
        self,
        mock_strategy: CDCAStrategy,
    ) -> None:
        """Test that invalid side raises ValueError."""
        with pytest.raises(ValueError, match="Unknown side: invalid!"):
            mock_strategy._get_order_price("invalid", 50000.0)

    def test_check_extra_sell_order_does_nothing(
        self,
        mock_strategy: CDCAStrategy,
    ) -> None:
        """Test that _check_extra_sell_order does nothing (no implementation needed)."""
        # This should not raise any exception
        mock_strategy._check_extra_sell_order()

    @patch("kraken_infinity_grid.strategies.c_dca.LOG")
    def test_new_sell_order_dry_run(
        self,
        mock_log: MagicMock,
        mock_strategy: CDCAStrategy,
    ) -> None:
        """Test new sell order in dry run mode."""
        mock_strategy._config.dry_run = True

        mock_strategy._new_sell_order(50000.0)

        mock_log.info.assert_called_once_with("Dry run, not placing sell order.")
        mock_strategy._orderbook_table.remove.assert_not_called()

    @patch("kraken_infinity_grid.strategies.c_dca.LOG")
    def test_new_sell_order_with_txid_to_delete(
        self,
        mock_log: MagicMock,
        mock_strategy: CDCAStrategy,
    ) -> None:
        """Test new sell order with txid to delete."""
        txid = "test_txid_123"

        mock_strategy._new_sell_order(50000.0, txid_to_delete=txid)

        mock_log.debug.assert_called_once_with("cDCA strategy, not placing sell order.")
        mock_strategy._orderbook_table.remove.assert_called_once_with(
            filters={"txid": txid},
        )

    @patch("kraken_infinity_grid.strategies.c_dca.LOG")
    def test_new_sell_order_without_txid(
        self,
        mock_log: MagicMock,
        mock_strategy: CDCAStrategy,
    ) -> None:
        """Test new sell order without txid to delete."""
        mock_strategy._new_sell_order(50000.0)

        mock_log.debug.assert_called_once_with("cDCA strategy, not placing sell order.")
        mock_strategy._orderbook_table.remove.assert_not_called()
