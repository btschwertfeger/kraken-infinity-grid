#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Unit tests for the SetupManager class."""

from unittest import mock

import pytest

from kraken_infinity_grid.gridbot import KrakenInfinityGridBot
from kraken_infinity_grid.setup import SetupManager


@pytest.fixture
def strategy() -> mock.Mock:
    """Fixture to create a mock strategy."""
    strategy = mock.Mock(spec=KrakenInfinityGridBot)
    strategy.userref = 13456789
    strategy.user = mock.Mock()
    strategy.market = mock.Mock()
    strategy.configuration = mock.Mock()
    strategy.orderbook = mock.Mock()
    strategy.om = mock.Mock()
    strategy.t = mock.Mock()
    return strategy


@pytest.fixture
def setup_manager(strategy: mock.Mock) -> SetupManager:
    """Fixture to create a SetupManager instance for testing."""
    return SetupManager(strategy)


# ==============================================================================


def test_init(setup_manager: SetupManager, strategy: mock.Mock) -> None:
    """Test the initialization of SetupManager."""
    assert setup_manager._SetupManager__s == strategy


def test_update_orderbook_get_open_orders(
    setup_manager: SetupManager,
    strategy: mock.Mock,
) -> None:
    """Test retrieving open orders from upstream."""
    strategy.user.get_open_orders.return_value = {
        "open": {
            "txid1": {"descr": {"pair": "BTC/USD"}},
            "txid2": {"descr": {"pair": "BTC/USD"}},
        },
    }
    strategy.altname = "BTC/USD"

    open_orders, open_txids = (
        setup_manager._SetupManager__update_orderbook_get_open_orders()
    )

    assert len(open_orders) == 2
    assert len(open_txids) == 2
    assert open_orders[0]["txid"] == "txid1"
    assert open_orders[1]["txid"] == "txid2"


def test_update_order_book_handle_closed_buy_order(
    setup_manager: SetupManager,
    strategy: mock.Mock,
) -> None:
    """
    Test handling a closed order buy order which will trigger placing a new sell
    order.
    """
    strategy.symbol = "BTC/USD"
    strategy.quote_currency = "USD"
    strategy.base_currency = "BTC"
    strategy.get_order_price.return_value = 51000.0

    local_order = {"txid": "txid1"}
    closed_order = {
        "descr": {"type": "buy"},
        "price": "50000",
        "vol_exec": "0.1",
    }

    setup_manager._SetupManager__update_order_book_handle_closed_order(
        local_order,
        closed_order,
    )

    strategy.t.send_to_telegram.assert_called_once()
    strategy.om.handle_arbitrage.assert_called_once_with(
        side="sell",
        order_price=51000.0,
        txid_id_to_delete="txid1",
    )


def test_update_order_book_handle_closed_sell_order_trigger_new_buy(
    setup_manager: SetupManager,
    strategy: mock.Mock,
) -> None:
    """
    Test handling a closed sell order for the case of another existing sell
    order.

    We need to distinguish between the case of having another sell order and the
    case of not having another sell order since if there is no other sell order,
    the algorithm would cancel the placed buy order anyways, so that's why we
    need to test both cases.
    """
    strategy.symbol = "BTC/USD"
    strategy.quote_currency = "USD"
    strategy.base_currency = "BTC"
    strategy.get_order_price.return_value = 49000.0
    strategy.orderbook.get_orders.return_value.all.return_value = [
        {"txid": "txid3", "side": "sell"},
    ]

    local_order = {"txid": "txid2"}
    closed_order = {
        "descr": {"type": "sell"},
        "price": "48000",
        "vol_exec": "0.1",
    }

    setup_manager._SetupManager__update_order_book_handle_closed_order(
        local_order,
        closed_order,
    )

    strategy.t.send_to_telegram.assert_called_once()
    strategy.om.handle_arbitrage.assert_called_once_with(
        side="buy",
        order_price=49000.0,
        txid_id_to_delete="txid2",
    )


def test_update_order_book_handle_closed_sell_order_no_new_buy(
    setup_manager: SetupManager,
    strategy: mock.Mock,
) -> None:
    """
    Test handling a closed sell order for the case of not existing other sell
    orders.

    We need to distinguish between the case of having another sell order and the
    case of not having another sell order since if there is no other sell order,
    the algorithm would cancel the placed buy order anyways, so that's why we
    need to test both cases.
    """
    strategy.symbol = "BTC/USD"
    strategy.quote_currency = "USD"
    strategy.base_currency = "BTC"
    strategy.get_order_price.return_value = 49000.0
    strategy.orderbook.get_orders.return_value.all.return_value = []

    local_order = {"txid": "txid2"}
    closed_order = {
        "descr": {"type": "sell"},
        "price": "48000",
        "vol_exec": "0.1",
    }

    setup_manager._SetupManager__update_order_book_handle_closed_order(
        local_order,
        closed_order,
    )

    strategy.t.send_to_telegram.assert_called_once()
    strategy.orderbook.remove.assert_called_once_with(
        filters={"txid": "txid2"},
    )


def test_update_order_book(
    setup_manager: SetupManager,
    strategy: mock.Mock,
) -> None:
    """
    Test updating the order book.

    * ensuring sync of upstream orders with local order book
    * handling closed orders (filled and canceled orders)
    """

    # These are the upstream orders:
    strategy.user.get_open_orders.return_value = {
        "open": {
            "txid1": {"descr": {"pair": "BTC/USD"}},
            "txid2": {"descr": {"pair": "BTC/USD"}},
        },
    }
    strategy.altname = "BTC/USD"
    strategy.orderbook.get_orders.side_effect = [
        # This is the local order book:
        mock.Mock(all=mock.Mock(return_value=[{"txid": "txid3"}, {"txid": "txid4"}])),
        # This are the updated local orders:
        [{"txid": "txid3"}, {"txid": "txid4"}],
    ]
    strategy.om.get_orders_info_with_retry.side_effect = [
        {"status": "canceled"},
        {"status": "closed"},
    ]

    setup_manager._SetupManager__update_order_book_handle_closed_order = mock.Mock()
    setup_manager._SetupManager__update_order_book()

    # Ensure that the upstream orders were added to the local orderbook
    strategy.orderbook.add.assert_any_call(
        {"descr": {"pair": "BTC/USD"}, "txid": "txid1"},
    )
    strategy.orderbook.add.assert_any_call(
        {"descr": {"pair": "BTC/USD"}, "txid": "txid2"},
    )
    assert strategy.orderbook.add.call_count == 2

    # Ensure that a filled order triggers the correct handling
    strategy.orderbook.remove.assert_called_once_with(filters={"txid": "txid3"})
    setup_manager._SetupManager__update_order_book_handle_closed_order.assert_called_once_with(
        local_order={"txid": "txid4"},
        closed_order={"status": "closed"},
    )


@pytest.mark.wip
@pytest.mark.parametrize(
    "input_fee,asset_fee,order_size",  # noqa: PT006
    [(None, 0.0026, 100.26), (0.02, 0.02, 102)],
)
def test_check_asset_pair_parameter(
    input_fee: float,
    asset_fee: float,
    order_size: float,
    setup_manager: SetupManager,
    strategy: mock.Mock,
) -> None:
    """
    Test checking the asset pair parameters.
    Maybe to white-boxy, but we need to ensure that the correct parameters are
    set in the strategy instance.
    """
    strategy.market.get_asset_pairs.return_value = {
        "BTCUSD": {
            "fees_maker": [[0, 0.26]],
            "altname": "BTC/USD",
            "base": "XXBT",
            "quote": "ZEUR",
            "cost_decimals": 5,
        },
    }
    strategy.symbol = "BTC/USD"
    strategy.amount_per_grid = 100
    strategy.fee = input_fee

    setup_manager._SetupManager__check_asset_pair_parameter()

    assert strategy.fee == asset_fee
    assert strategy.altname == "BTC/USD"
    assert strategy.zbase_currency == "XXBT"
    assert strategy.xquote_currency == "ZEUR"
    assert strategy.cost_decimals == 5
    assert strategy.amount_per_grid_plus_fee == pytest.approx(order_size)


def test_check_configuration_changes(
    setup_manager: SetupManager,
    strategy: mock.Mock,
) -> None:
    """Test checking configuration changes."""
    strategy.amount_per_grid = 10
    strategy.configuration.get.return_value = {"amount_per_grid": 5, "interval": 0.01}
    strategy.interval = 2

    setup_manager._SetupManager__check_configuration_changes()

    strategy.configuration.update.assert_any_call({"amount_per_grid": 10})
    strategy.configuration.update.assert_any_call({"interval": 2})
    strategy.om.cancel_all_open_buy_orders.assert_called_once()


def test_check_configuration_changes_no_changes(
    setup_manager: SetupManager,
    strategy: mock.Mock,
) -> None:
    """Test checking configuration changes."""
    strategy.amount_per_grid = 10
    strategy.configuration.get.return_value = {"amount_per_grid": 10, "interval": 0.02}
    strategy.interval = 0.02

    setup_manager._SetupManager__check_configuration_changes()

    strategy.configuration.update.assert_not_called()
    strategy.configuration.update.assert_not_called()
    strategy.om.cancel_all_open_buy_orders.assert_not_called()


def test_prepare_for_trading(
    setup_manager: SetupManager,
    strategy: mock.Mock,
) -> None:
    """Test preparing for trading."""
    strategy.symbol = "BTC/USD"
    strategy.name = "TestBot"
    strategy.market.get_ticker.return_value = {"BTCUSD": {"c": ["50000"]}}
    strategy.orderbook.get_orders.return_value = []

    setup_manager._SetupManager__check_asset_pair_parameter = mock.Mock()
    setup_manager._SetupManager__check_configuration_changes = mock.Mock()
    setup_manager.prepare_for_trading()

    strategy.t.send_to_telegram.assert_called_once()
    strategy.om.assign_all_pending_transactions.assert_called_once()
    strategy.om.add_missed_sell_orders.assert_called_once()
    strategy.om.check_price_range.assert_called_once()
    setup_manager._SetupManager__check_asset_pair_parameter.assert_called_once()
    setup_manager._SetupManager__check_configuration_changes.assert_called_once()
    assert strategy.is_ready_to_trade
    assert strategy.init_done
