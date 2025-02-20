# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from pathlib import Path

import pytest


@pytest.fixture
def sqlite_file(tmp_path: Path) -> Path:
    """
    Fixture to create a Path object to the SQLite database file.

    This is used during tests in order to create isolated databases.
    """
    Path(tmp_path).mkdir(exist_ok=True)
    return tmp_path / "kraken_infinity_grid.sqlite"


@pytest.fixture
def db_config(sqlite_file: Path) -> dict:
    """Fixture to create a mock database configuration."""
    return {
        "db_user": "",
        "db_password": "",
        "db_host": "",
        "db_port": "",
        "db_name": "kraken_infinity_grid",
        "sqlite_file": sqlite_file,
    }
