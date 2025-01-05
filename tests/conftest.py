#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2024 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Module providing fixtures for the test suites."""

from unittest import mock

import pytest

from kraken_infinity_grid.telegram import Telegram


@pytest.fixture
def telegram() -> Telegram:
    """Fixture to create a Telegram instance for testing."""
    strategy = mock.Mock()
    telegram_token = "test_token"  # noqa: S105
    telegram_chat_id = "test_chat_id"
    exception_token = "exception_token"  # noqa: S105
    exception_chat_id = "exception_chat_id"
    return Telegram(
        strategy,
        telegram_token,
        telegram_chat_id,
        exception_token,
        exception_chat_id,
    )
