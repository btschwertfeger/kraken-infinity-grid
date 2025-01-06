#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Unit tests for the database module."""


from pathlib import Path

import pytest

from kraken_infinity_grid.database import (
    Configuration,
    DBConnect,
    Orderbook,
    PendingIXIDs,
    UnsoldBuyOrderTXIDs,
)


@pytest.fixture
def db_connect(sqlite_file: Path) -> DBConnect:
    """
    Fixture to create a DBConnect instance with an in-memory SQLite database.
    """
    return DBConnect(sqlite_file=sqlite_file)


@pytest.fixture
def orderbook(db_connect: DBConnect) -> Orderbook:
    """Fixture to create an Orderbook instance for testing."""
    orderbook = Orderbook(userref=123456789, db=db_connect)
    db_connect.init_db()
    return orderbook


@pytest.fixture
def configuration(db_connect: DBConnect) -> Configuration:
    """Fixture to create a Configuration instance for testing."""
    configuration = Configuration(userref=123456789, db=db_connect)
    db_connect.init_db()
    return configuration


@pytest.fixture
def unsold_buy_order_txids(db_connect: DBConnect) -> UnsoldBuyOrderTXIDs:
    """Fixture to create an UnsoldBuyOrderTXIDs instance for testing."""
    unsold_buy_order_txids = UnsoldBuyOrderTXIDs(userref=123456789, db=db_connect)
    db_connect.init_db()
    return unsold_buy_order_txids


@pytest.fixture
def pending_txids(db_connect: DBConnect) -> PendingIXIDs:
    """Fixture to create a PendingIXIDs instance for testing."""
    pending_txids = PendingIXIDs(userref=123456789, db=db_connect)
    db_connect.init_db()
    return pending_txids


# ==============================================================================


def test_db_connect_init(db_connect: DBConnect) -> None:
    """Test the initialization of DBConnect."""
    assert db_connect.engine is not None
    assert db_connect.session is not None
    assert db_connect.metadata is not None


def test_orderbook_add(orderbook: Orderbook, db_connect: DBConnect) -> None:
    """Test adding an order to the orderbook."""
    order = {
        "txid": "txid1",
        "descr": {"pair": "BTC/USD", "type": "buy", "price": "50000"},
        "vol": "0.1",
    }
    orderbook.add(order)
    result = db_connect.get_rows(
        orderbook._Orderbook__table,
        filters={"txid": "txid1"},
    )
    assert result.fetchone() is not None


def test_orderbook_get_orders(
    orderbook: Orderbook,
) -> None:
    """Test getting orders from the orderbook."""
    order = {
        "txid": "txid1",
        "descr": {"pair": "BTC/USD", "type": "buy", "price": "50000"},
        "vol": "0.1",
    }
    orderbook.add(order)
    result = orderbook.get_orders(filters={"txid": "txid1"})
    assert result.fetchone() is not None


def test_orderbook_remove(orderbook: Orderbook, db_connect: DBConnect) -> None:
    """Test removing orders from the orderbook."""
    order = {
        "txid": "txid1",
        "descr": {"pair": "BTC/USD", "type": "buy", "price": "50000"},
        "vol": "0.1",
    }
    orderbook.add(order)
    orderbook.remove(filters={"txid": "txid1"})
    result = db_connect.get_rows(
        orderbook._Orderbook__table,
        filters={"txid": "txid1"},
    )
    assert result.fetchone() is None


def test_orderbook_update(orderbook: Orderbook, db_connect: DBConnect) -> None:
    """Test updating orders in the orderbook."""
    order = {
        "txid": "txid1",
        "descr": {"pair": "BTC/USD", "type": "buy", "price": "50000"},
        "vol": "0.1",
    }
    orderbook.add(order)
    updates = {
        "txid": "txid1",
        "descr": {"pair": "BTC/USD", "type": "buy", "price": "51000"},
        "vol": "0.2",
    }
    orderbook.update(updates, filters={"txid": "txid1"})
    result = db_connect.get_rows(
        orderbook._Orderbook__table,
        filters={"txid": "txid1"},
    )
    updated_order = result.fetchone()
    assert updated_order is not None
    assert updated_order["side"] == "buy"
    assert updated_order["price"] == 51000.0
    assert updated_order["volume"] == 0.2


def test_orderbook_count(orderbook: Orderbook) -> None:
    """Test counting orders in the orderbook."""
    order1 = {
        "txid": "txid1",
        "descr": {"pair": "BTC/USD", "type": "buy", "price": "50000"},
        "vol": "0.1",
    }
    order2 = {
        "txid": "txid2",
        "descr": {"pair": "BTC/USD", "type": "buy", "price": "50000"},
        "vol": "0.1",
    }
    orderbook.add(order1)
    count = orderbook.count()
    assert count == 1
    orderbook.add(order2)
    count = orderbook.count()
    assert count == 2
    count = orderbook.count(filters={"txid": "txid1"})
    assert count == 1


def test_configuration_get(configuration: Configuration) -> None:
    """Test getting configuration from the table."""
    result = configuration.get()
    assert result["price_of_highest_buy"] == 0.0


def test_configuration_update(configuration: Configuration) -> None:
    """Test updating configuration in the table."""
    updates = {"amount_per_grid": 10}
    configuration.update(updates)
    result = configuration.get(filters={"amount_per_grid": 10})
    assert result["amount_per_grid"] == 10


def test_unsold_buy_order_txids_add(
    unsold_buy_order_txids: UnsoldBuyOrderTXIDs,
    db_connect: DBConnect,
) -> None:
    """Test adding an unsold buy order txid to the table."""
    unsold_buy_order_txids.add(txid="txid1", price=50000.0)
    result = db_connect.get_rows(
        unsold_buy_order_txids._UnsoldBuyOrderTXIDs__table,
        filters={"txid": "txid1"},
    )
    assert result.fetchone()["txid"] == "txid1"


def test_unsold_buy_order_txids_remove(
    unsold_buy_order_txids: UnsoldBuyOrderTXIDs,
    db_connect: DBConnect,
) -> None:
    """Test removing an unsold buy order txid from the table."""
    unsold_buy_order_txids.add(txid="txid1", price=50000.0)
    unsold_buy_order_txids.remove(txid="txid1")
    result = db_connect.get_rows(
        unsold_buy_order_txids._UnsoldBuyOrderTXIDs__table,
        filters={"txid": "txid1"},
    )
    assert result.fetchone() is None


def test_unsold_buy_order_txids_get(
    unsold_buy_order_txids: UnsoldBuyOrderTXIDs,
) -> None:
    """Test getting unsold buy order txids from the table."""
    unsold_buy_order_txids.add(txid="txid1", price=50000.0)
    result = unsold_buy_order_txids.get(filters={"txid": "txid1"})
    assert result.fetchone()["txid"] == "txid1"


def test_unsold_buy_order_txids_count(
    unsold_buy_order_txids: UnsoldBuyOrderTXIDs,
) -> None:
    """Test counting unsold buy order txids from the table."""
    unsold_buy_order_txids.add(txid="txid1", price=50000.0)

    count = unsold_buy_order_txids.count()
    assert count == 1

    unsold_buy_order_txids.add(txid="txid2", price=50000.0)
    count = unsold_buy_order_txids.count()
    assert count == 2

    count = unsold_buy_order_txids.count(filters={"txid": "txid1"})
    assert count == 1


def test_pending_txids_add(
    pending_txids: PendingIXIDs,
    db_connect: DBConnect,
) -> None:
    """Test adding a pending txid to the table."""
    pending_txids.add(txid="txid1")
    result = db_connect.get_rows(
        pending_txids._PendingIXIDs__table,
        filters={"txid": "txid1"},
    )
    assert result.fetchone()["txid"] == "txid1"


def test_pending_txids_remove(
    pending_txids: PendingIXIDs,
    db_connect: DBConnect,
) -> None:
    """Test removing a pending txid from the table."""
    pending_txids.add(txid="txid1")
    pending_txids.remove(txid="txid1")
    result = db_connect.get_rows(
        pending_txids._PendingIXIDs__table,
        filters={"txid": "txid1"},
    )
    assert result.fetchone() is None


def test_pending_txids_get(pending_txids: PendingIXIDs) -> None:
    """Test getting pending txids from the table."""
    pending_txids.add(txid="txid1")
    result = pending_txids.get(filters={"txid": "txid1"})
    assert result.fetchone()["txid"] == "txid1"


def test_pending_txids_count(pending_txids: PendingIXIDs) -> None:
    """Test counting pending txids from the table."""
    pending_txids.add(txid="txid1")
    count = pending_txids.count()
    assert count == 1

    pending_txids.add(txid="txid2")
    count = pending_txids.count()
    assert count == 2

    count = pending_txids.count(filters={"txid": "txid1"})
    assert count == 1
