#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Module implementing the database connection and handling of interactions."""

from datetime import datetime
from importlib.metadata import version
from logging import getLogger
from typing import Any, Self

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    asc,
    create_engine,
    delete,
    desc,
    func,
    select,
    text,
    update,
)
from sqlalchemy.engine.result import MappingResult
from sqlalchemy.orm import sessionmaker

LOG = getLogger(__name__)


class DBConnect:
    """Class handling the connection to the PostgreSQL or sqlite database."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self: Self,
        db_user: str | None = None,
        db_password: str | None = None,
        db_host: str | None = None,
        db_port: str | int | None = None,
        db_name: str = "kraken_infinity_grid",
        in_memory: bool = False,
        sqlite_file: str | None = None,
    ) -> None:
        LOG.info("Connecting to the database...")
        if in_memory:
            engine = "sqlite:///:memory:"
        elif sqlite_file:
            engine = f"sqlite:///{sqlite_file}"
        else:
            engine = "postgresql://"
            if db_user and db_password:
                engine += f"{db_user}:{db_password}@"
            if db_host and db_port:
                engine += f"{db_host}:{db_port}"
            engine += f"/{db_name}"

        self.engine = create_engine(engine)
        self.session = sessionmaker(bind=self.engine)()
        self.metadata = MetaData()

    def init_db(self: Self) -> None:
        """Create tables if they do not exist and pre-fill with default rows."""
        LOG.info("- Initializing tables...")
        self.metadata.create_all(self.engine)
        LOG.info("- Database initialized.")

    def add_row(self: Self, table: Table, **kwargs: Any) -> None:
        """Insert a row into the specified table."""
        LOG.debug("Inserting a row into '%s': %s", table, kwargs)
        self.session.execute(table.insert().values(**kwargs))
        self.session.commit()

    def get_rows(
        self: Self,
        table: Table,
        filters: dict | None = None,
        exclude: dict | None = None,
        order_by: tuple[str, str] | None = None,  # (column_name, "asc" or "desc")
        limit: int | None = None,
    ) -> MappingResult:
        """Fetch rows from the specified table with optional filters, ordering, and limit."""
        LOG.debug(
            "Querying rows from table '%s' with filters: %s, order_by: %s, limit: %s",
            table,
            filters,
            order_by,
            limit,
        )
        query = select(table)
        if filters:
            query = query.where(
                *(table.c[column] == value for column, value in filters.items()),
            )
        if exclude:
            query = query.where(
                *(table.c[column] != value for column, value in exclude.items()),
            )
        if order_by:
            column, direction = order_by
            if direction.lower() == "asc":
                query = query.order_by(asc(table.c[column]))
            elif direction.lower() == "desc":
                query = query.order_by(desc(table.c[column]))
        if limit:
            query = query.limit(limit)
        return self.session.execute(query).mappings()

    def update_row(
        self: Self,
        table: Table,
        filters: dict,
        updates: dict,
    ) -> None:
        """Update rows in the specified table matching filters."""
        LOG.debug("Update rows from '%s': %s :: %s", table, filters, updates)
        query = (
            update(table)
            .where(*(table.c[column] == value for column, value in filters.items()))
            .values(**updates)
        )
        self.session.execute(query)
        self.session.commit()

    def delete_row(self: Self, table: Table, filters: dict) -> None:
        """Delete rows from the specified table matching filters."""
        LOG.debug("Deleting row(s) from '%s': %s", table, filters)
        query = delete(table).where(
            *(table.c[column] == value for column, value in filters.items()),
        )
        self.session.execute(query)
        self.session.commit()


class Orderbook:
    """Table containing the orderbook data."""

    def __init__(self: Self, userref: int, db: DBConnect) -> None:
        LOG.debug("Initializing the orderbook table...")
        self.__db = db
        self.__userref = userref
        self.__table = Table(
            "orderbook",
            db.metadata,
            Column("id", Integer, primary_key=True),
            Column("userref", Integer, nullable=False),
            Column("txid", String, nullable=False),
            Column("symbol", String, nullable=False),
            Column("side", String, nullable=False),
            Column("price", Float, nullable=False),
            Column("volume", Float, nullable=False),
        )

    def add(self: Self, order: dict) -> None:
        """Add an order to the orderbook."""
        LOG.debug("Adding order to the orderbook: %s", order)
        self.__db.add_row(
            self.__table,
            userref=self.__userref,
            txid=order["txid"],
            symbol=order["descr"]["pair"],
            side=order["descr"]["type"],
            price=order["descr"]["price"],
            volume=order["vol"],
        )

    def get_orders(
        self: Self,
        filters: dict | None = None,
        exclude: dict | None = None,
        order_by: tuple[str, str] | None = None,
        limit: int | None = None,
    ) -> MappingResult:
        """Get orders from the orderbook."""
        LOG.debug(
            "Getting orders from the orderbook with filters: %s, exclude: %s, order_by: %s, limit: %s",
            filters,
            exclude,
            order_by,
            limit,
        )
        if not filters:
            filters = {}
        return self.__db.get_rows(
            self.__table,
            filters=filters | {"userref": self.__userref},
            exclude=exclude,
            order_by=order_by,
            limit=limit,
        )

    def remove(self: Self, filters: dict) -> None:
        """Remove orders from the orderbook."""
        LOG.debug("Removing orders from the orderbook: %s", filters)
        if not filters:
            raise ValueError("Filters required for removal in orderbook")
        self.__db.delete_row(
            self.__table,
            filters=filters | {"userref": self.__userref},
        )

    def update(self: Self, updates: dict, filters: dict | None = None) -> None:
        """
        Update orders in the orderbook.

        In case one manually modifies the order. This is not recommended!
        """
        LOG.debug("Updating orders in the orderbook: %s :: %s", filters, updates)
        if not filters:
            filters = {}

        prepared_updates = {}
        if "txid" in updates:
            prepared_updates["txid"] = updates["txid"]

        if descr := updates.get("descr"):
            if descr.get("pair"):
                prepared_updates["symbol"] = descr["pair"]
            if descr.get("type"):
                prepared_updates["side"] = descr["type"]  # should not happen
            if descr.get("price"):
                prepared_updates["price"] = descr["price"]

        if "vol" in updates:
            prepared_updates["volume"] = updates["vol"]

        self.__db.update_row(
            self.__table,
            filters=filters | {"userref": self.__userref},
            updates=prepared_updates,
        )

    def count(
        self: Self,
        filters: dict | None = None,
        exclude: dict | None = None,
    ) -> int:
        """Count orders in the orderbook."""
        LOG.debug(
            "Counting orders in the orderbook with filters: %s and exclude: %s",
            filters,
            exclude,
        )
        if not filters:
            filters = {}
        filters |= {"userref": self.__userref}

        query = (
            select(func.count())  # pylint: disable=not-callable
            .select_from(self.__table)
            .where(
                *(self.__table.c[column] == value for column, value in filters.items()),
            )
        )
        if exclude:
            query = query.where(
                *(self.__table.c[column] != value for column, value in exclude.items()),
            )
        return self.__db.session.execute(query).scalar()  # type: ignore[no-any-return]


class Configuration:
    """Table containing information about the bots config."""

    def __init__(self: Self, userref: int, db: DBConnect) -> None:
        LOG.debug("Initializing the configuration table...")
        self.__db = db
        self.__userref = userref
        self.__table = Table(
            "configuration",
            self.__db.metadata,
            Column("id", Integer, primary_key=True),
            Column("userref", Integer, nullable=False),
            Column(
                "version",
                String,
                nullable=False,
                default=version("kraken-infinity-grid"),
            ),
            Column("vol_of_unfilled_remaining", Float, nullable=False, default=0),
            Column(
                "vol_of_unfilled_remaining_max_price",
                Float,
                nullable=False,
                default=0,
            ),
            Column("price_of_highest_buy", Float, nullable=False, default=0),
            Column("amount_per_grid", Float),
            Column("interval", Float),
            Column("last_price_time", DateTime, nullable=False),
            Column("last_telegram_update", DateTime, nullable=False),
            extend_existing=True,
        )

        # Create if not exist
        self.__table.create(bind=self.__db.engine, checkfirst=True)

        # self.__migrate_table()

        # Add initial values
        if not self.__db.get_rows(
            self.__table,
            filters={"userref": self.__userref},
        ).fetchone():  # type: ignore[no-untyped-call]
            self.__db.add_row(
                self.__table,
                userref=self.__userref,
                last_price_time=datetime.now(),
                last_telegram_update=datetime.now(),
            )

    def __migrate_table(self: Self) -> None:
        """
        Migrate the table to the latest version.

        This method may be extended to handle more complex migrations in the
        future, for now its just a placeholder.
        """
        LOG.info("- Check for %s table migration...", self.__table.name)
        any_change = False

        # ======================================================================
        # Renaming columns
        ##
        change_column = text(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = :table_name"
            " AND column_name = :column_name",
        )
        if not self.__db.session.execute(
            change_column,
            {"table_name": self.__table.name, "column_name": "version"},
        ).fetchone():
            LOG.info(
                "  - Adding column 'version' to %s table...",
                self.__table.name,
            )
            self.__db.session.execute(
                text(
                    f"ALTER TABLE {self.__table.name} ADD COLUMN version VARCHAR",
                ),
            )
            any_change = True

        if not self.__db.session.execute(
            change_column,
            {"table_name": self.__table.name, "column_name": "amount_per_grid"},
        ).fetchone():
            LOG.info(
                "  - Adding column 'amount_per_grid' to %s table...",
                self.__table.name,
            )
            self.__db.session.execute(
                text(
                    f"ALTER TABLE {self.__table.name}"
                    " ADD COLUMN amount_per_grid FLOAT",
                ),
            )
            any_change = True

        if not self.__db.session.execute(
            change_column,
            {"table_name": self.__table.name, "column_name": "interval"},
        ).fetchone():
            LOG.info("  - Adding column 'interval' to %s table...", self.__table.name)
            self.__db.session.execute(
                text(f"ALTER TABLE {self.__table.name} ADD COLUMN interval FLOAT"),
            )
            any_change = True

        self.__db.session.execute(
            text(
                f"UPDATE {self.__table.name}"  # noqa: S608
                " SET version = :version WHERE userref = :userref",
            ),
            {"version": version("kraken-infinity-grid"), "userref": self.__userref},
        )

        if any_change:
            LOG.info("  - Migration of %s table successfully!", self.__table.name)

    def get(self: Self, filters: dict | None = None) -> dict:
        """Get configuration from the table."""
        LOG.debug(
            "Getting configuration from the table 'configuration' with filter: %s",
            filters,
        )
        if not filters:
            filters = {}

        if result := self.__db.get_rows(
            self.__table,
            filters=filters | {"userref": self.__userref},
        ):
            return next(result)
        raise ValueError(f"No configuration found for passed {filters=}!")

    def update(self: Self, updates: dict) -> None:
        """Update configuration in the table."""
        LOG.debug("Updating configuration in the table: %s", updates)
        self.__db.update_row(
            self.__table,
            filters={"userref": self.__userref},
            updates=updates,
        )


class UnsoldBuyOrderTXIDs:
    """
    Table containing information about future sell orders. Entries are added
    before placing a new sell order in order to not miss the placement in case
    placing fails.

    If the placement succeeds, the entry gets deleted from this table.
    """

    def __init__(self: Self, userref: int, db: DBConnect) -> None:
        LOG.debug("Initializing the UnsoldBuyOrderTXIDs table...")
        self.__db = db
        self.__userref = userref
        self.__table = Table(
            "unsold_buy_order_txids",
            self.__db.metadata,
            Column("id", Integer, primary_key=True),
            Column("userref", Integer, nullable=False),
            Column("txid", String, nullable=False),  # corresponding buy order
            Column("price", Float, nullable=False),  # price at which to sell
        )

    def add(self: Self, txid: str, price: float) -> None:
        """Add a missed sell order to the table."""
        LOG.debug(
            "Adding unsold buy order txid to the 'unsold_buy_order_txids' table: %s",
            txid,
        )
        self.__db.add_row(
            self.__table,
            userref=self.__userref,
            txid=txid,
            price=price,
        )

    def remove(self: Self, txid: str) -> None:
        """Remove txid from the table."""
        LOG.debug(
            "Removing unsold buy order txid from the 'unsold_buy_order_txids'"
            " table: %s",
            txid,
        )
        self.__db.delete_row(
            self.__table,
            filters={
                "userref": self.__userref,
                "txid": txid,
            },
        )

    def get(self: Self, filters: dict | None = None) -> MappingResult:
        """Retrieve unsold buy order txids from the table."""
        LOG.debug(
            "Retrieving unsold buy order txids from the"
            " 'unsold_buy_order_txids' table with filters: %s",
            filters,
        )
        if not filters:
            filters = {}
        return self.__db.get_rows(
            self.__table,
            filters=filters | {"userref": self.__userref},
        )

    def count(self: Self, filters: dict | None = None) -> int:
        """Count unsold buy order txids from the table."""
        LOG.debug(
            "Count unsold buy order txids from the table unsold_buy_order_txids"
            " table with filters: %s",
            filters,
        )
        if not filters:
            filters = {}
        filters |= {"userref": self.__userref}

        query = (
            select(func.count())  # pylint: disable=not-callable
            .select_from(self.__table)
            .where(
                *(self.__table.c[column] == value for column, value in filters.items()),
            )
        )
        return self.__db.session.execute(query).scalar()  # type: ignore[no-any-return]


class PendingIXIDs:
    """
    Table containing pending TXIDs. TXIDs are pending for the time from being
    placed to processed by Kraken. Usually an order gets placed, the TXID is
    returned and stored in this table. Then the algorithm fetches this 'pending'
    TXID to retrieve the full order information in order to add these to the
    local orderbook. After that, the TXID gets removed from this table.
    """

    def __init__(self: Self, userref: int, db: DBConnect) -> None:
        LOG.debug("Initializing the PendingIXIDs table...")
        self.__db = db
        self.__userref = userref
        self.__table = Table(
            "pending_txids",
            self.__db.metadata,
            Column("id", Integer, primary_key=True),
            Column("userref", Integer, nullable=False),
            Column("txid", String, nullable=False),
        )

    def get(self: Self, filters: dict | None = None) -> MappingResult:
        """Get pending orders from the table."""
        LOG.debug(
            "Getting pending orders from the 'pending_txids' table with filters: %s",
            filters,
        )
        if not filters:
            filters = {}

        return self.__db.get_rows(
            self.__table,
            filters=filters | {"userref": self.__userref},
        )

    def add(self: Self, txid: str) -> None:
        """Add a pending order to the table."""
        LOG.debug(
            "Adding a pending txid to the 'pending_txids' table: %s",
            txid,
        )
        self.__db.add_row(
            self.__table,
            userref=self.__userref,
            txid=txid,
        )

    def remove(self: Self, txid: str) -> None:
        """Remove a pending order from the table."""
        LOG.debug("Removing pending txid from the 'pending_txids' table: %s", txid)
        self.__db.delete_row(
            self.__table,
            filters={"userref": self.__userref, "txid": txid},
        )

    def count(self: Self, filters: dict | None = None) -> int:
        """Count pending orders in the table."""
        LOG.debug(
            "Counting pending txids of the 'pending_txids' table with filters: %s",
            filters,
        )
        if not filters:
            filters = {}
        filters |= {"userref": self.__userref}

        query = (
            select(func.count())  # pylint: disable=not-callable
            .select_from(self.__table)
            .where(
                *(self.__table.c[column] == value for column, value in filters.items()),
            )
        )
        return self.__db.session.execute(query).scalar()  # type: ignore[no-any-return]
