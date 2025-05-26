# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

import logging
from unittest import mock

import pytest_asyncio
from kraken.spot import Market

from kraken_infinity_grid.core.gridbot import KrakenInfinityGridBot

from .helper import KrakenAPI


@pytest_asyncio.fixture
async def instance(config: dict, db_config: dict) -> KrakenInfinityGridBot:
    """Fixture to create a KrakenInfinityGridBot instance for testing."""
    instance = KrakenInfinityGridBot(
        key="key",
        secret="secret",
        config=config,
        db_config=db_config,
    )
    # We don't need to test for telegram messages here...
    instance.t.send_to_telegram = lambda message, exception=False, log=True: (
        logging.getLogger().info(message)
        if log and not exception
        else logging.getLogger().error(message) if exception and log else None
    )

    # Mock the Kraken clients as we're not interacting with the Kraken API
    api = KrakenAPI()
    instance.user = api
    instance.market = mock.MagicMock(spec=Market)
    instance.trade = api

    # Define static asset pair parameters
    instance.market.get_asset_pairs.return_value = {
        "XXBTZUSD": {
            "fees_maker": [
                [0, 0.25],
                [10000, 0.2],
                [50000, 0.14],
                [100000, 0.12],
                [250000, 0.1],
                [500000, 0.08],
                [1000000, 0.06],
                [2500000, 0.04],
                [5000000, 0.02],
                [10000000, 0.0],
            ],
            "altname": "BTCUSD",
            "base": "XXBT",
            "quote": "ZUSD",
            "cost_decimals": 5,
        },
    }
    yield instance
    await instance.stop()
    await instance.async_close()
