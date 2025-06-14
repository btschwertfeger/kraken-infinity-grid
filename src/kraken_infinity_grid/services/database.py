# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

"""Module implementing the database connection and handling of interactions."""

from logging import getLogger
from typing import Any, Self

from sqlalchemy import MetaData, Table, asc, create_engine, delete, desc, select, update
from sqlalchemy.engine.result import MappingResult
from sqlalchemy.orm import sessionmaker

from kraken_infinity_grid.models.dto import DBConfigDTO

LOG = getLogger(__name__)


class DBConnect:
    """Class handling the connection to the PostgreSQL or sqlite database."""

    def __init__(  # pylint: disable=too-many-positional-arguments
        self: Self,
        config: DBConfigDTO,
    ) -> None:
        # db_user: str | None = None,
        # db_password: str | None = None,
        # db_host: str | None = None,
        # db_port: str | int | None = None,
        # db_name: str = "kraken_infinity_grid",
        # in_memory: bool = False,
        # sqlite_file: str | None = None,

        LOG.info("Connecting to the database...")
        # if in_memory:
        #     engine = "sqlite:///:memory:"
        if config.sqlite_file:
            engine = f"sqlite:///{config.sqlite_file}"
        else:
            engine = "postgresql://"
            if config.db_user and config.db_password:
                engine += f"{config.db_user}:{config.db_password}@"
            if config.db_host and config.db_port:
                engine += f"{config.db_host}:{config.db_port}"
            engine += f"/{config.db_name}"

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

    def close(self: Self) -> None:
        """Close database connections properly to avoid resource leaks."""
        LOG.info("Closing database connections...")
        if hasattr(self, "session") and self.session:
            self.session.close()
        if hasattr(self, "engine") and self.engine:
            self.engine.dispose()
        LOG.info("Database connections closed.")
