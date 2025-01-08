#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Unit tests for the OrderManager class."""

import sys
from unittest import mock

import pytest

from kraken_infinity_grid.gridbot import KrakenInfinityGridBot
from kraken_infinity_grid.order_management import OrderManager


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
    strategy.trade = mock.Mock()
    strategy.pending_txids = mock.Mock()
    strategy.unsold_buy_order_txids = mock.Mock()
    strategy.get_balances = mock.Mock()
    strategy.get_value_of_orders = mock.Mock()
    strategy.get_current_buy_prices = mock.Mock()
    strategy.get_active_buy_orders = mock.Mock()
    strategy.get_active_sell_orders = mock.Mock()
    strategy.get_orders_info_with_retry = mock.Mock()
    strategy.save_exit = mock.Mock()
    strategy.dry_run = False
    strategy.max_investment = 10000
    strategy.amount_per_grid = 100
    strategy.interval = 0.01
    strategy.fee = 0.0026
    strategy.symbol = "BTC/USD"
    strategy.altname = "BTCUSD"
    strategy.base_currency = "BTC"
    strategy.quote_currency = "USD"
    strategy.cost_decimals = 5
    strategy.ticker = mock.Mock()
    strategy.ticker.last = 50000.0
    strategy.save_exit = sys.exit
    return strategy


@pytest.fixture
def order_manager(strategy: mock.Mock) -> OrderManager:
    """Fixture to create an OrderManager instance for testing."""
    return OrderManager(strategy)


# ==============================================================================


@mock.patch.object(OrderManager, "handle_arbitrage")
def test_add_missed_sell_orders(
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test adding missed sell orders."""
    strategy.unsold_buy_order_txids.get.return_value = [
        {"txid": "txid1", "price": 50000.0},
        {"txid": "txid2", "price": 51000.0},
    ]
    order_manager.add_missed_sell_orders()
    mock_handle_arbitrage.assert_any_call(
        side="sell",
        order_price=50000.0,
        txid_id_to_delete="txid1",
    )
    mock_handle_arbitrage.assert_any_call(
        side="sell",
        order_price=51000.0,
        txid_id_to_delete="txid2",
    )
    assert mock_handle_arbitrage.call_count == 2


@mock.patch.object(OrderManager, "assign_order_by_txid")
def test_assign_all_pending_transactions(
    mock_assign_order_by_txid: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test assigning all pending transactions."""
    strategy.pending_txids.get.return_value = [
        {"txid": "txid1"},
        {"txid": "txid2"},
    ]
    order_manager.assign_all_pending_transactions()

    mock_assign_order_by_txid.assert_any_call(txid="txid1")
    mock_assign_order_by_txid.assert_any_call(txid="txid2")
    assert mock_assign_order_by_txid.call_count == 2


def test_assign_order_by_txid(
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test assigning an order by txid."""
    strategy.user.get_orders_info.return_value = {
        "txid1": {"txid": "txid1", "status": "open"},
    }
    strategy.pending_txids.get.return_value.all.return_value = [{"txid": "txid1"}]
    order_manager.assign_order_by_txid(txid="txid1")
    strategy.orderbook.add.assert_called_once_with(
        {"txid": "txid1", "status": "open"},
    )
    strategy.pending_txids.remove.assert_called_once_with("txid1")


def test_assign_order_by_txid_retry(
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test retrying to assign an order by txid."""
    strategy.user.get_orders_info.side_effect = [
        {},
        {"txid1": {"txid": "txid1", "status": "open"}},
    ]
    strategy.pending_txids.get.return_value.all.return_value = [
        {"txid": "txid1"},
    ]

    with mock.patch(
        "kraken_infinity_grid.order_management.sleep",
        return_value=None,
    ):
        order_manager.assign_order_by_txid(txid="txid1")

    strategy.orderbook.add.assert_called_once_with(
        {"txid": "txid1", "status": "open"},
    )
    strategy.pending_txids.remove.assert_called_once_with("txid1")


@mock.patch.object(OrderManager, "assign_all_pending_transactions")
def test_check_pending_txids(
    mock_assign_all_pending_transactions: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test checking pending txids."""
    strategy.pending_txids.count.return_value = 1
    assert order_manager._OrderManager__check_pending_txids() is True

    strategy.pending_txids.count.return_value = 0
    assert order_manager._OrderManager__check_pending_txids() is False

    mock_assign_all_pending_transactions.assert_called_once()


# ==============================================================================
# check_near_buy_orders
##


@mock.patch.object(OrderManager, "handle_cancel_order")
def test_check_near_buy_orders_cancel(
    mock_handle_cancel_order: mock.Mock,  # noqa: ARG001
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test checking near buy orders to cancel orders to close to each other."""
    strategy.get_current_buy_prices.return_value = [50000.0, 49950.0, 49940.0]
    strategy.get_active_buy_orders.return_value = [
        {"txid": "txid1", "price": 50000.0},
        {"txid": "txid2", "price": 49950.0},
        {"txid": "txid3", "price": 49940.0},
    ]
    order_manager._OrderManager__check_near_buy_orders()
    order_manager.handle_cancel_order.assert_any_call(txid="txid1")
    order_manager.handle_cancel_order.assert_any_call(txid="txid2")
    assert order_manager.handle_cancel_order.call_count == 2


@mock.patch.object(OrderManager, "handle_cancel_order")
def test_check_near_buy_orders_good_distance(
    mock_handle_cancel_order: mock.Mock,  # noqa: ARG001
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test checking near buy orders to not close orders if they are good in place.
    """
    strategy.get_current_buy_prices.return_value = [50000.0, 49500.0, 49005]
    order_manager._OrderManager__check_near_buy_orders()
    strategy.get_active_buy_orders.assert_not_called()


@mock.patch.object(OrderManager, "handle_cancel_order")
def test_check_near_buy_orders_cancel_no_buys(
    mock_handle_cancel_order: mock.Mock,  # noqa: ARG001
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test checking near buy orders to do nothing if there are no open buy orders.
    """
    strategy.get_current_buy_prices.return_value = []
    order_manager._OrderManager__check_near_buy_orders()
    strategy.get_active_buy_orders.assert_not_called()


# ==============================================================================
# check_n_open_buy_orders
##


@mock.patch.object(OrderManager, "handle_arbitrage")
def test_check_n_open_buy_orders(
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test checking the number of open buy orders.

    The scenario already has 1 open buy order, so 4 more buy orders should be
    placed.
    """
    # Number of desired open buy orders
    strategy.n_open_buy_orders = 5
    # Current investment
    strategy.investment = 1000.0
    strategy.max_investment_reached = False
    # The currently available quote currency
    strategy.get_balances.return_value = {"quote_available": 10000.0}
    # No pending transactions
    strategy.pending_txids.count.return_value = 0
    # The buy prices before each following buy order is placed
    strategy.get_current_buy_prices.side_effect = [
        [50000.0],
        [50000.0, 49900.0],
        [50000.0, 49900.0, 49800.0],
        [50000.0, 49900.0, 49800.0, 49700.0],
        [50000.0, 49900.0, 49800.0, 49700.0, 49600.0],
    ]
    # The buy prices for each following buy order
    strategy.get_order_price.side_effect = [49900.0, 49800.0, 49700.0, 49600.0]
    # The orders that are currently open
    strategy.get_active_buy_orders.return_value.all.side_effect = [
        [
            {"txid": "txid1", "price": 50000.0},
        ],
        [
            {"txid": "txid1", "price": 50000.0},
            {"txid": "txid2", "price": 49900.0},
        ],
        [
            {"txid": "txid1", "price": 50000.0},
            {"txid": "txid2", "price": 49900.0},
            {"txid": "txid3", "price": 49800.0},
        ],
        [
            {"txid": "txid1", "price": 50000.0},
            {"txid": "txid2", "price": 49900.0},
            {"txid": "txid3", "price": 49800.0},
            {"txid": "txid4", "price": 49700.0},
        ],
        [
            {"txid": "txid1", "price": 50000.0},
            {"txid": "txid2", "price": 49900.0},
            {"txid": "txid3", "price": 49800.0},
            {"txid": "txid4", "price": 49700.0},
            {"txid": "txid4", "price": 49600.0},
        ],
    ]

    order_manager._OrderManager__check_n_open_buy_orders()
    for price in (49900.0, 49800.0, 49700.0, 49600.0):
        mock_handle_arbitrage.assert_any_call(
            side="buy",
            order_price=price,
        )
    assert mock_handle_arbitrage.call_count == 4


@mock.patch.object(OrderManager, "handle_arbitrage")
def test_check_n_open_buy_orders_max_investment_reached(
    mock_handle_arbitrage: mock.Mock,
    strategy: mock.Mock,
) -> None:
    """
    Test checking that the function does not place any order if the maximum
    investment is reached.
    """
    strategy.max_investment_reached = True

    # Ensure no API call is made in order to avoid rate-limiting
    strategy.get_balances.assert_not_called()
    # Ensure no buy orders are placed
    mock_handle_arbitrage.assert_not_called()


# ==============================================================================


@mock.patch.object(OrderManager, "handle_cancel_order")
def test_check_lowest_cancel_of_more_than_n_buy_orders(
    mock_handle_cancel_order: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test checking and canceling the lowest buy order if there are more than n
    open buy orders."""
    strategy.n_open_buy_orders = 1
    strategy.get_current_buy_prices.side_effect = [
        [50000.0, 49900.0, 49800.0],
        [50000.0, 49900.0],
        [50000.0],
    ]
    strategy.get_active_buy_orders.return_value.all.return_value = [
        {"txid": "txid1", "price": 50000.0},
        {"txid": "txid2", "price": 49900.0},
        {"txid": "txid3", "price": 49800.0},
    ]
    order_manager._OrderManager__check_lowest_cancel_of_more_than_n_buy_orders()
    mock_handle_cancel_order.assert_any_call(txid="txid2")
    mock_handle_cancel_order.assert_any_call(txid="txid3")
    assert mock_handle_cancel_order.call_count == 2


@mock.patch.object(OrderManager, "check_price_range")
@mock.patch.object(OrderManager, "cancel_all_open_buy_orders")
def test_shift_buy_orders_up(
    mock_cancel_all_open_buy_orders: mock.Mock,
    mock_check_price_range: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test shifting buy orders up."""
    strategy.get_current_buy_prices.return_value = [50000.0, 49000.0]
    strategy.get_active_buy_orders.return_value.all.return_value = [
        {"txid": "txid1", "price": 50000.0},
        {"txid": "txid2", "price": 49000.0},
    ]
    strategy.ticker.last = 60000.0
    assert order_manager._OrderManager__shift_buy_orders_up() is True
    mock_cancel_all_open_buy_orders.assert_called_once()
    mock_check_price_range.assert_called_once()


@mock.patch.object(OrderManager, "handle_arbitrage")
def test_check_extra_sell_order(
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test checking and placing an extra sell order for the SWING strategy."""
    strategy.strategy = "GridHODL"
    strategy.get_active_sell_orders.return_value.all.return_value = []
    strategy.get_balances.return_value = {"base_available": 1.0}
    strategy.get_order_price.return_value = 51000.0

    order_manager._OrderManager__check_extra_sell_order()
    mock_handle_arbitrage.assert_not_called()

    strategy.strategy = "SWING"
    order_manager._OrderManager__check_extra_sell_order()
    mock_handle_arbitrage.assert_called_once_with(
        side="sell",
        order_price=51000.0,
    )


@mock.patch.object(OrderManager, "_OrderManager__check_pending_txids")
@mock.patch.object(OrderManager, "_OrderManager__check_near_buy_orders")
@mock.patch.object(OrderManager, "_OrderManager__check_n_open_buy_orders")
@mock.patch.object(
    OrderManager,
    "_OrderManager__check_lowest_cancel_of_more_than_n_buy_orders",
)
@mock.patch.object(OrderManager, "_OrderManager__shift_buy_orders_up")
@mock.patch.object(OrderManager, "_OrderManager__check_extra_sell_order")
def test_check_price_range(
    mock_check_extra_sell_order: mock.Mock,
    mock_shift_buy_orders_up: mock.Mock,
    mock_check_lowest_cancel_of_more_than_n_buy_orders: mock.Mock,
    mock_check_n_open_buy_orders: mock.Mock,
    mock_check_near_buy_orders: mock.Mock,
    mock_check_pending_txids: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test checking the price range. Quite white-box testing, but there is no
    other way at this place.
    """
    # Return if dryrun is enabled
    strategy.dry_run = True
    order_manager.check_price_range()
    mock_check_pending_txids.assert_not_called()

    # Return if there are pending transactions
    strategy.dry_run = False
    mock_check_pending_txids.return_value = True
    order_manager.check_price_range()
    mock_check_pending_txids.assert_called_once()
    mock_check_near_buy_orders.assert_not_called()

    # Run parts of the function if there are no pending transactions
    mock_check_pending_txids.return_value = False
    mock_check_pending_txids.count.return_value = 1
    order_manager.check_price_range()
    mock_check_near_buy_orders.assert_called_once()
    mock_check_n_open_buy_orders.assert_called_once()
    mock_check_lowest_cancel_of_more_than_n_buy_orders.assert_not_called()

    # Run more checks of no pending transactions
    mock_check_pending_txids.count.return_value = 0
    strategy.pending_txids.count.return_value = 0
    mock_shift_buy_orders_up.return_value = True
    order_manager.check_price_range()
    mock_check_lowest_cancel_of_more_than_n_buy_orders.assert_called_once()
    mock_shift_buy_orders_up.assert_called_once()
    mock_check_extra_sell_order.assert_not_called()

    # Check place extra sell order otherwise
    mock_shift_buy_orders_up.return_value = False
    order_manager.check_price_range()
    mock_check_extra_sell_order.assert_called_once()


@mock.patch.object(OrderManager, "new_buy_order")
@mock.patch.object(OrderManager, "new_sell_order")
def test_handle_arbitrage(
    mock_new_sell_order: mock.Mock,
    mock_new_buy_order: mock.Mock,
    order_manager: OrderManager,
) -> None:
    """Test handling arbitrage."""
    order_manager.handle_arbitrage(side="buy", order_price=50000.0)
    mock_new_buy_order.assert_called_once_with(
        order_price=50000.0,
        txid_to_delete=None,
    )

    order_manager.handle_arbitrage(side="sell", order_price=51000.0)
    mock_new_sell_order.assert_called_once_with(
        order_price=51000.0,
        txid_id_to_delete=None,
    )

    with pytest.raises(ValueError, match=r".*Invalid side.*"):
        order_manager.handle_arbitrage(side="invalid", order_price=50000.0)


# ==============================================================================
# new_buy_order
##


def test_new_buy_order(
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test placing a new buy order successfully."""
    strategy.get_balances.return_value = {"quote_available": 1000.0}
    strategy.max_investment = 6000.0
    strategy.max_investment_reached = False
    strategy.get_value_of_orders.return_value = 5000.0
    strategy.trade.create_order.return_value = {"txid": ["txid1"]}
    strategy.trade.truncate.side_effect = [50000.0, 100.0]  # price, volume

    order_manager.new_buy_order(order_price=50000.0)
    strategy.pending_txids.add.assert_called_once_with("txid1")
    strategy.trade.create_order.assert_called_once()
    strategy.om.assign_order_by_txid.assert_called_once_with("txid1")


def test_new_buy_order_max_invest_reached(
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test placing a new buy order without sufficient funds."""
    strategy.max_investment_reached = True

    order_manager.new_buy_order(order_price=50000.0)
    strategy.trade.create_order.assert_not_called()
    strategy.pending_txids.add.assert_not_called()


def test_new_buy_order_not_enough_funds(
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test placing a new buy order without sufficient funds."""
    strategy.get_balances.return_value = {"quote_available": 0.0}
    strategy.get_value_of_orders.return_value = 5000.0
    strategy.trade.create_order.return_value = {"txid": ["txid1"]}
    strategy.trade.truncate.side_effect = [50000.0, 100.0]  # price, volume

    order_manager.new_buy_order(order_price=50000.0)
    strategy.trade.create_order.assert_not_called()
    strategy.pending_txids.add.assert_not_called()


# ==============================================================================
# new_sell_order
##
def test_new_sell_order_skip_dca(
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test placing a new sell order - skip for DCA strategy."""
    strategy.strategy = "DCA"
    order_manager.new_sell_order(order_price=51000.0, txid_id_to_delete="txid1")
    strategy.orderbook.remove.assert_called_once_with(filters={"txid": "txid1"})
    strategy.trade.create_order.assert_not_called()
    strategy.pending_txids.add.assert_not_called()


def test_new_sell_order_GridSell(
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test placing a new sell order with the GridSell strategy and remove the
    corresponding buy order txid from tracking.

    TODO: Check for correct values in volume and order price - maybe?
    """
    strategy.strategy = "GridSell"
    strategy.get_balances.return_value = {"base_available": 1.0}

    # Handling the txid to delete
    strategy.unsold_buy_order_txids.get.return_value.all.return_value = []

    # The unsold buy order of which the volume is now to be sold
    strategy.user.get_orders_info.return_value = {
        "txid1": {"status": "closed", "vol_exec": 0.1},
    }
    # The price and volume of the unsold buy order (volume equals vol_exec for
    # GridSell)
    strategy.trade.truncate.side_effect = [0.1, 52000.0]  # volume, price
    strategy.trade.create_order.return_value = {"txid": ["txid2"]}

    order_manager.new_sell_order(order_price=52000.0, txid_id_to_delete="txid1")

    # == Ensure that unsold buy orders are temporarily saved
    strategy.unsold_buy_order_txids.add.assert_called_once_with(
        txid="txid1",
        price=52000.0,
    )

    # == Ensure sell order was placed
    strategy.trade.create_order.assert_called_once()

    # == Ensure adding to pending txids
    strategy.pending_txids.add.assert_called_once_with("txid2")

    # == Ensure old buy order gets removed from orderbook and unsold buy orders
    strategy.orderbook.remove.assert_called_once_with(filters={"txid": "txid1"})
    strategy.unsold_buy_order_txids.remove.assert_called_once_with(txid="txid1")

    strategy.trade.create_order.return_value = {"txid": ["txid2"]}
    strategy.pending_txids.add.assert_called_once_with("txid2")
    strategy.om.assign_order_by_txid.assert_called_once_with(txid="txid2")


@pytest.mark.parametrize("strategy_name", ["SWING", "GridHODL"])
def test_new_sell_order_GridHODL_SWING(
    order_manager: OrderManager,
    strategy: mock.Mock,
    strategy_name: str,
) -> None:
    """
    Test placing a new sell order with the GridHODL and SWING strategies and
    remove the corresponding buy order txid from tracking.

    TODO: Check for correct values in volume and order price - maybe?
    """
    strategy.strategy = strategy_name
    strategy.get_balances.return_value = {"base_available": 1.0}

    # Handling the txid to delete
    strategy.unsold_buy_order_txids.get.return_value.all.return_value = []

    # The unsold buy order of which the volume is now to be sold
    strategy.user.get_orders_info.return_value = {
        "txid1": {"status": "closed", "vol_exec": 0.1},
    }

    # The price and volume of the unsold buy order
    strategy.trade.truncate.side_effect = [52000.0, 0.1]  # price, volume
    strategy.trade.create_order.return_value = {"txid": ["txid2"]}

    order_manager.new_sell_order(order_price=52000.0, txid_id_to_delete="txid1")

    # == Ensure that unsold buy orders are temporarily saved
    strategy.unsold_buy_order_txids.add.assert_called_once_with(
        txid="txid1",
        price=52000.0,
    )

    # == Ensure sell order was placed
    strategy.trade.create_order.assert_called_once()

    # == Ensure adding to pending txids
    strategy.pending_txids.add.assert_called_once_with("txid2")

    # == Ensure old buy order gets removed from orderbook and unsold buy orders
    strategy.orderbook.remove.assert_called_once_with(filters={"txid": "txid1"})
    strategy.unsold_buy_order_txids.remove.assert_called_once_with(txid="txid1")

    strategy.trade.create_order.return_value = {"txid": ["txid2"]}
    strategy.pending_txids.add.assert_called_once_with("txid2")
    strategy.om.assign_order_by_txid.assert_called_once_with(txid="txid2")


@pytest.mark.parametrize("strategy_name", ["SWING", "GridHODL"])
def test_new_sell_order_GridHODL_SWING_not_enough_funds(
    order_manager: OrderManager,
    strategy: mock.Mock,
    strategy_name: str,
) -> None:
    """
    Test placing a new sell order with the GridHODL and SWING strategies and
    ensuring proper handling if there are not enough funds to place the sell
    order.
    """
    strategy.strategy = strategy_name
    strategy.get_balances.return_value = {"base_available": 0.0}

    # Handling the txid to delete
    strategy.unsold_buy_order_txids.get.return_value.all.return_value = []

    # The unsold buy order of which the volume is now to be sold
    strategy.user.get_orders_info.return_value = {
        "txid1": {"status": "closed", "vol_exec": 0.1},
    }

    # The price and volume of the unsold buy order
    strategy.trade.truncate.side_effect = [52000.0, 0.1]  # price, volume
    strategy.trade.create_order.return_value = {"txid": ["txid2"]}

    order_manager.new_sell_order(order_price=52000.0, txid_id_to_delete="txid1")

    # == Ensure that unsold buy orders are temporarily saved
    strategy.unsold_buy_order_txids.add.assert_called_once_with(
        txid="txid1",
        price=52000.0,
    )

    # == Ensure not creating order
    strategy.trade.create_order.assert_not_called()

    # == Ensure not adding to pending txids
    strategy.pending_txids.add.assert_not_called()

    # == Ensure that the old buy order gets removed from orderbook, as it is now
    #    tracked in unsold buy orders table.
    strategy.unsold_buy_order_txids.remove.assert_not_called()
    strategy.orderbook.remove.assert_called_once_with(filters={"txid": "txid1"})


# ==============================================================================
# test_handle_filled_order_event
##
@mock.patch.object(OrderManager, "handle_arbitrage")
@mock.patch.object(OrderManager, "get_orders_info_with_retry")
def test_handle_filled_order_event_buy(
    mock_get_orders_info_with_retry: mock.Mock,
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test handling a filled order event."""
    mock_get_orders_info_with_retry.return_value = {
        "descr": {
            "pair": "BTCUSD",
            "type": "buy",
            "price": 50000.0,
        },
        "status": "closed",
        "userref": 13456789,
        "vol_exec": 0.1,
    }
    strategy.get_order_price.return_value = 51000.0
    order_manager.handle_filled_order_event(txid="txid1")

    strategy.t.send_to_telegram.assert_called_once()
    mock_handle_arbitrage.assert_called_once_with(
        side="sell",
        order_price=51000.0,
        txid_id_to_delete="txid1",
    )


@mock.patch.object(OrderManager, "handle_arbitrage")
@mock.patch.object(OrderManager, "get_orders_info_with_retry")
def test_handle_filled_order_event_sell_place_new_buy(
    mock_get_orders_info_with_retry: mock.Mock,
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test handling a filled sell order event - placing a new sell order only
    if there is another existing sell order.
    """
    mock_get_orders_info_with_retry.return_value = {
        "descr": {
            "pair": "BTCUSD",
            "type": "sell",
            "price": 50000.0,
        },
        "status": "closed",
        "userref": 13456789,
        "vol_exec": 0.1,
    }
    strategy.get_active_sell_orders.return_value.all.return_value = [
        {
            "txid": "txid1",
            "side": "sell",
        },
    ]
    strategy.get_order_price.return_value = 51000.0
    order_manager.handle_filled_order_event(txid="txid2")

    strategy.t.send_to_telegram.assert_called_once()
    mock_handle_arbitrage.assert_called_once_with(
        side="buy",
        order_price=51000.0,
        txid_id_to_delete="txid2",
    )


@mock.patch.object(OrderManager, "handle_arbitrage")
@mock.patch.object(OrderManager, "get_orders_info_with_retry")
def test_handle_filled_order_event_sell_place_no_new_buy(
    mock_get_orders_info_with_retry: mock.Mock,
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test handling a filled sell order event - not placing a sell order if there
    are no other existing sell orders.
    """
    mock_get_orders_info_with_retry.return_value = {
        "descr": {
            "pair": "BTCUSD",
            "type": "sell",
            "price": 50000.0,
        },
        "status": "closed",
        "userref": 13456789,
        "vol_exec": 0.1,
    }
    strategy.get_active_sell_orders.return_value.all.return_value = []
    strategy.get_order_price.return_value = 51000.0
    order_manager.handle_filled_order_event(txid="txid2")

    strategy.t.send_to_telegram.assert_called_once()
    mock_handle_arbitrage.assert_not_called()


@mock.patch.object(OrderManager, "get_orders_info_with_retry")
@mock.patch.object(OrderManager, "handle_arbitrage")
def test_handle_filled_order_event_buy_failing_order_retrieval(
    mock_handle_arbitrage: mock.Mock,
    mock_get_orders_info_with_retry: mock.Mock,
    order_manager: OrderManager,
) -> None:
    """
    Test handling a filled order event failing if the order can't be retrieved.
    """
    mock_get_orders_info_with_retry.return_value = None

    with pytest.raises(SystemExit):
        order_manager.handle_filled_order_event(txid="txid1")

    mock_handle_arbitrage.assert_not_called()


@mock.patch.object(OrderManager, "get_orders_info_with_retry")
@mock.patch.object(OrderManager, "handle_arbitrage")
def test_handle_filled_order_event_buy_order_not_from_instance(
    mock_handle_arbitrage: mock.Mock,
    mock_get_orders_info_with_retry: mock.Mock,
    order_manager: OrderManager,
) -> None:
    """
    Test handling a filled order event ignoring if the event was not from this
    instance.
    """
    mock_get_orders_info_with_retry.return_value = {
        "descr": {"pair": "BTCUSD", "type": "buy", "price": 50000.0},
        "status": "closed",
        "userref": -13456789,
        "vol_exec": 0.1,
    }
    order_manager.handle_filled_order_event(txid="txid1")
    mock_handle_arbitrage.assert_not_called()


@mock.patch.object(OrderManager, "get_orders_info_with_retry")
@mock.patch.object(OrderManager, "handle_arbitrage")
def test_handle_filled_order_event_buy_order_not_closed_retry(
    mock_handle_arbitrage: mock.Mock,
    mock_get_orders_info_with_retry: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test handling a filled order event failing if the fetched order is not
    closed.
    """
    mock_get_orders_info_with_retry.side_effect = [
        {
            "descr": {"pair": "BTCUSD", "type": "buy", "price": 50000.0},
            "status": "open",
            "userref": 13456789,
            "vol_exec": 0.1,
        }
        for _ in range(3)
    ] + [
        {
            "descr": {"pair": "BTCUSD", "type": "buy", "price": 50000.0},
            "status": "closed",
            "userref": 13456789,
            "vol_exec": 0.1,
        },
    ]

    strategy.get_order_price.return_value = 51000.0
    with mock.patch("kraken_infinity_grid.order_management.sleep", return_value=None):
        order_manager.handle_filled_order_event(txid="txid1")

    strategy.t.send_to_telegram.assert_called_once()
    mock_handle_arbitrage.assert_called_once_with(
        side="sell",
        order_price=51000.0,
        txid_id_to_delete="txid1",
    )


@mock.patch.object(OrderManager, "get_orders_info_with_retry")
@mock.patch.object(OrderManager, "handle_arbitrage")
def test_handle_filled_order_event_buy_order_not_closed_retry_failing(
    mock_handle_arbitrage: mock.Mock,
    mock_get_orders_info_with_retry: mock.Mock,
    order_manager: OrderManager,
) -> None:
    """
    Test handling a filled order event failing due to too much retries of
    retrieving the order information.
    """
    mock_get_orders_info_with_retry.side_effect = [
        {
            "descr": {"pair": "BTCUSD", "type": "buy", "price": 50000.0},
            "status": "open",
            "userref": 13456789,
            "vol_exec": 0.1,
        }
        for _ in range(4)
    ]

    with (
        pytest.raises(SystemExit, match=r".*fetched order is not closed.*"),
        mock.patch("kraken_infinity_grid.order_management.sleep", return_value=None),
    ):
        order_manager.handle_filled_order_event(txid="txid1")

    mock_handle_arbitrage.assert_not_called()


@mock.patch.object(OrderManager, "get_orders_info_with_retry")
@mock.patch.object(OrderManager, "handle_arbitrage")
def test_handle_filled_order_event_buy_dry_run(
    mock_handle_arbitrage: mock.Mock,
    mock_get_orders_info_with_retry: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test handling a filled order event ignoring if the event the algorithm runs
    in dryrun.
    """
    mock_get_orders_info_with_retry.return_value = {
        "descr": {"pair": "BTCUSD", "type": "buy", "price": 50000.0},
        "status": "closed",
        "userref": 13456789,
        "vol_exec": 0.1,
    }
    strategy.dry_run = True
    strategy.get_order_price.return_value = 50000.0
    order_manager.handle_filled_order_event(txid="txid1")

    strategy.t.send_to_telegram.assert_not_called()
    mock_handle_arbitrage.assert_not_called()


# ==============================================================================
# handle_cancel_order
##
@mock.patch.object(OrderManager, "handle_arbitrage")
def test_handle_cancel_order_partly_filled_create_sell_order(
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test handling a cancel order that is partly filled and creates a sell order.
    """
    strategy.user.get_orders_info.return_value = {
        "txid1": {
            "descr": {"pair": "BTCUSD", "type": "buy", "price": "50000"},
            "vol_exec": "0.1",
        },
    }
    strategy.configuration.get.return_value = {
        "vol_of_unfilled_remaining": 0.1,
        "vol_of_unfilled_remaining_max_price": 50000.0,
    }

    order_manager.handle_cancel_order(txid="txid1")

    # == Ensure cancellation of the order
    strategy.trade.cancel_order.assert_called_once_with(txid="txid1")

    # == Ensure removal from the orderbook
    strategy.orderbook.remove.assert_called_once_with(filters={"txid": "txid1"})

    # == Ensure to first update the volume that was partly filled
    strategy.configuration.update.assert_any_call({"vol_of_unfilled_remaining": 0.2})

    # Ensure the exceeding volume is sold
    mock_handle_arbitrage.assert_called_once()

    # == Ensure to update the saved volume
    strategy.configuration.update.assert_any_call(
        {"vol_of_unfilled_remaining": 0, "vol_of_unfilled_remaining_max_price": 0},
    )

    assert strategy.configuration.update.call_count == 2


@mock.patch.object(OrderManager, "handle_arbitrage")
def test_handle_cancel_order_dry_run(
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test handling a cancel order in dry run mode."""
    strategy.dry_run = True
    strategy.configuration.get.return_value = {
        "vol_of_unfilled_remaining": 0.1,
        "vol_of_unfilled_remaining_max_price": 50000.0,
    }
    strategy.user.get_orders_info.return_value = {
        "txid1": {
            "descr": {"pair": "BTCUSD", "type": "buy", "price": "50000"},
            "vol_exec": "0.1",
        },
    }
    order_manager.handle_cancel_order(txid="txid1")
    strategy.trade.cancel_order.assert_not_called()
    strategy.orderbook.remove.assert_not_called()
    mock_handle_arbitrage.assert_not_called()
    strategy.configuration.update.assert_not_called()


@mock.patch.object(OrderManager, "handle_arbitrage")
def test_handle_cancel_order_not_matching_pair(
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test handling a cancel order with a non-matching pair."""
    strategy.user.get_orders_info.return_value = {
        "txid1": {
            "descr": {"pair": "ETHUSD", "type": "buy", "price": "50000"},
            "vol_exec": "0.1",
        },
    }
    order_manager.handle_cancel_order(txid="txid1")
    strategy.trade.cancel_order.assert_not_called()
    strategy.orderbook.remove.assert_not_called()
    mock_handle_arbitrage.assert_not_called()
    strategy.configuration.update.assert_not_called()


@mock.patch.object(OrderManager, "handle_arbitrage")
def test_handle_cancel_order_partly_filled(
    mock_handle_arbitrage: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """
    Test handling a cancel order that is partly filled but not enough to create
    a new sell order.
    """
    # Ensure the grid amount to higher than the volume unfilled
    strategy.amount_per_grid = 10000.0
    strategy.user.get_orders_info.return_value = {
        "txid1": {
            "descr": {"pair": "BTCUSD", "type": "buy", "price": "50000"},
            "vol_exec": "0.1",
        },
    }
    strategy.configuration.get.return_value = {
        "vol_of_unfilled_remaining": 0.1,
        "vol_of_unfilled_remaining_max_price": 49000.0,
    }
    order_manager.handle_cancel_order(txid="txid1")
    strategy.trade.cancel_order.assert_called_once_with(txid="txid1")
    strategy.orderbook.remove.assert_called_once_with(filters={"txid": "txid1"})
    strategy.configuration.update.assert_called_once_with(
        {
            "vol_of_unfilled_remaining": 0.2,
            "vol_of_unfilled_remaining_max_price": 50000.0,
        },
    )
    mock_handle_arbitrage.assert_not_called()


def test_handle_cancel_order_exception(
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test handling a cancel order with an exception."""
    strategy.user.get_orders_info.side_effect = Exception("Test exception")
    with pytest.raises(SystemExit, match="Test exception"):
        order_manager.handle_cancel_order(txid="txid1")


@mock.patch.object(OrderManager, "handle_cancel_order")
def test_cancel_all_open_buy_orders(
    mock_handle_cancel_order: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test canceling all open buy orders."""

    # Check for multiple orders in the orderbook
    strategy.user.get_open_orders.return_value = {
        "open": {
            "txid1": {
                "descr": {
                    "type": "buy",
                    "pair": "BTCUSD",
                },
            },
            "txid2": {
                "descr": {
                    "type": "buy",
                    "pair": "BTCUSD",
                },
            },
            "txid3": {
                "descr": {
                    "type": "buy",
                    "pair": "ETHUSD",
                },
            },
            "txid4": {
                "descr": {
                    "type": "sell",
                    "pair": "BTCUSD",
                },
            },
        },
    }

    with mock.patch(
        "kraken_infinity_grid.order_management.sleep",
        return_value=None,
    ):
        order_manager.cancel_all_open_buy_orders()

    mock_handle_cancel_order.assert_any_call(txid="txid1")
    mock_handle_cancel_order.assert_any_call(txid="txid2")
    assert mock_handle_cancel_order.call_count == 2


@mock.patch("kraken_infinity_grid.order_management.sleep", return_value=None)
def test_get_orders_info_with_retry_success(
    mock_sleep: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test successfully retrieving order info with retry."""
    strategy.user.get_orders_info.return_value = {"txid1": {"status": "closed"}}
    result = order_manager.get_orders_info_with_retry(txid="txid1")
    assert result == {"status": "closed"}
    strategy.user.get_orders_info.assert_called_once_with(txid="txid1")
    mock_sleep.assert_not_called()


@mock.patch("kraken_infinity_grid.order_management.sleep", return_value=None)
def test_get_orders_info_with_retry_retry_success(
    mock_sleep: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test retrying and successfully retrieving order info."""
    strategy.user.get_orders_info.side_effect = [
        {},
        {"txid1": {"status": "closed"}},
    ]
    result = order_manager.get_orders_info_with_retry(txid="txid1")
    assert result == {"status": "closed"}
    assert strategy.user.get_orders_info.call_count == 2
    mock_sleep.assert_called_once()


@mock.patch("kraken_infinity_grid.order_management.sleep", return_value=None)
def test_get_orders_info_with_retry_failure(
    mock_sleep: mock.Mock,
    order_manager: OrderManager,
    strategy: mock.Mock,
) -> None:
    """Test failing to retrieve order info after maximum retries."""
    strategy.user.get_orders_info.return_value = {}
    result = order_manager.get_orders_info_with_retry(txid="txid1", max_tries=3)
    assert result is None
    assert strategy.user.get_orders_info.call_count == 4
    assert mock_sleep.call_count == 4
