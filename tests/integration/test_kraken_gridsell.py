# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

import pytest, pytest_asyncio

from kraken_infinity_grid.models.dto.configuration import (
    BotConfigDTO,
)
from kraken_infinity_grid.core.engine import BotEngine
import logging
from kraken_infinity_grid.core.state_machine import States

from unittest import mock


@pytest.fixture(scope="module")
def kraken_gridsell_bot_config() -> BotConfigDTO:
    return BotConfigDTO(
        strategy="GridSell",
        exchange="Kraken",
        api_public_key="",
        api_secret_key="",
        name="Local Tests Bot GridSell",
        userref=0,
        base_currency="BTC",
        quote_currency="USD",
        max_investment=10000.0,
        amount_per_grid=100.0,
        interval=0.01,
        n_open_buy_orders=5,
    )

@pytest_asyncio.fixture
async def kraken_gridsell_instance(
    kraken_gridsell_bot_config, db_config, notification_config
) -> BotEngine:
    """
    Initialize the Bot Engine using the GridSell strategy and Kraken backend

    The Kraken API is mocked to avoid creating, modifying, or canceling real
    orders.
    """
    bot_config = kraken_gridsell_bot_config
    engine = BotEngine(
        bot_config=bot_config,
        db_config=db_config,
        notification_config=notification_config,
    )

    from kraken_infinity_grid.adapters.exchanges.kraken import (
        KrakenExchangeRESTServiceAdapter,
        KrakenExchangeWebsocketServiceAdapter,
    )
    from .helper import KrakenAPI

    # ==========================================================================
    ## Initialize the mocked REST API client
    engine._BotEngine__strategy._rest_api = KrakenExchangeRESTServiceAdapter(
        api_public_key=bot_config.api_public_key,
        api_secret_key=bot_config.api_secret_key,
        state_machine=engine._BotEngine__state_machine,
    )

    api = KrakenAPI()
    engine._BotEngine__strategy._rest_api._KrakenExchangeRESTServiceAdapter__user_service = (
        api
    )
    engine._BotEngine__strategy._rest_api._KrakenExchangeRESTServiceAdapter__trade_service = (
        api
    )
    engine._BotEngine__strategy._rest_api._KrakenExchangeRESTServiceAdapter__market_service = (
        api
    )

    # ==========================================================================
    ## Initialize the websocket client
    engine._BotEngine__strategy._GridHODLStrategy__ws_client = (
        KrakenExchangeWebsocketServiceAdapter(
            api_public_key=gridhodl_kraken_bot_config.api_public_key,
            api_secret_key=gridhodl_kraken_bot_config.api_secret_key,
            state_machine=engine._BotEngine__state_machine,
            event_bus=engine._BotEngine__event_bus,
        )
    )
    # Stop the connection directly
    await engine._BotEngine__strategy._GridHODLStrategy__ws_client.close()
    # Use the mocked API client
    engine._BotEngine__strategy._GridHODLStrategy__ws_client.__websocket_service = api

    # ==========================================================================
    ## Misc
    engine._BotEngine__strategy._exchange_domain = (
        engine._BotEngine__strategy._rest_api.get_exchange_domain()
    )

    yield engine


@pytest.mark.integration
@pytest.mark.asyncio
@mock.patch("kraken_infinity_grid.adapters.exchanges.kraken.sleep", return_value=None)
@mock.patch("kraken_infinity_grid.strategies.grid_hodl.sleep", return_value=None)
@mock.patch("kraken_infinity_grid.strategies.grid_base.sleep", return_value=None)
async def test_kraken_grid_hodl(
    mock_sleep1: mock.MagicMock,
    mock_sleep2: mock.MagicMock,
    mock_sleep3: mock.MagicMock,
    kraken_gridhodl_instance: BotEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Test the GridHODL strategy using pre-generated websocket messages.

    This one is very similar to GridSell, the main difference is the volume of
    sell orders.
    """
    caplog.set_level(logging.INFO)

    # Create engine using mocked Kraken API
    engine = kraken_gridhodl_instance
    state_machine = engine._BotEngine__state_machine
    strategy = engine._BotEngine__strategy
    ws_client = strategy._GridHODLStrategy__ws_client
    api = engine._BotEngine__strategy._GridHODLStrategy__ws_client.__websocket_service

    # ==========================================================================
    # During the following processing, the following steps are done:
    # 1. The algorithm prepares for trading (see setup)
    # 2. The order manager checks the price range
    # 3. The order manager checks for n open buy orders
    # 4. The order manager places new orders
    await ws_client.on_message(
        {
            "channel": "executions",
            "type": "snapshot",
            "data": [{"exec_type": "canceled", "order_id": "txid0"}],
        },
    )
    assert state_machine.state != States.ERROR
    assert strategy._ready_to_trade is False

    await api.on_ticker_update(callback=ws_client.on_message, last=50000.0)
    assert strategy._ticker == 50000.0
    assert state_machine.state != States.ERROR
    assert strategy._ready_to_trade is True

    # ==========================================================================
    # 1. PLACEMENT OF INITIAL N BUY ORDERS
    # After both fake-websocket channels are connected, the algorithm went
    # through its full setup and placed orders against the fake Kraken API and
    # finally saved those results into the local orderbook table.

    # Check if the five initial buy orders are placed with the expected price
    # and volume. Note that the interval is not exactly 0.01 due to the fee
    # which is taken into account.
    for order, price, volume in zip(
        strategy._orderbook_table.get_orders().all(),
        (49504.9, 49014.7, 48529.4, 48048.9, 47573.1),
        (0.00202, 0.0020402, 0.0020606, 0.00208121, 0.00210202),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == "buy"
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    # ==========================================================================
    # 2. SHIFTING UP BUY ORDERS
    # Check if shifting up the buy orders works
    await api.on_ticker_update(callback=ws_client.on_message, last=60000.0)
    assert strategy._ticker == 60000.0
    assert state_machine.state != States.ERROR

    # We should now still have 5 buy orders, but at a higher price. The other
    # orders should be canceled.
    for order, price, volume in zip(
        strategy._orderbook_table.get_orders().all(),
        (59405.9, 58817.7, 58235.3, 57658.7, 57087.8),
        (0.00168333, 0.00170016, 0.00171717, 0.00173434, 0.00175168),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == "buy"
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    # ==========================================================================
    # 3. FILLING A BUY ORDER
    # Now lets let the price drop a bit so that a buy order gets triggered.
    await api.on_ticker_update(callback=ws_client.on_message, last=59990.0)
    assert strategy._ticker == 59990.0
    assert state_machine.state != States.ERROR

    # Quick re-check ... the price update should not affect any orderbook
    # changes when dropping.
    for order, price, volume in zip(
        strategy._orderbook_table.get_orders().all(),
        (59405.9, 58817.7, 58235.3, 57658.7, 57087.8),
        (0.00168333, 0.00170016, 0.00171717, 0.00173434, 0.00175168),
        strict=False,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == "buy"
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    # Now trigger the execution of the first buy order
    await api.on_ticker_update(callback=ws_client.on_message, last=59000.0)
    assert state_machine.state != States.ERROR
    assert strategy._orderbook_table.count() == 5

    # Ensure that we have 4 buy orders and 1 sell order
    for order, price, volume, side in zip(
        strategy._orderbook_table.get_orders().all(),
        (58817.7, 58235.3, 57658.7, 57087.8, 59999.9),
        (0.00170016, 0.00171717, 0.00173434, 0.00175168, 0.00167504),
        ["buy"] * 4 + ["sell"],
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == side
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    # ==========================================================================
    # 4. ENSURING N OPEN BUY ORDERS
    # If there is a new price event, the algorithm will place the 5th buy order.
    await api.on_ticker_update(callback=ws_client.on_message, last=59100.0)
    assert state_machine.state != States.ERROR
    assert strategy._orderbook_table.count() == 6

    for order, price, volume, side in zip(
        strategy._orderbook_table.get_orders().all(),
        (58817.7, 58235.3, 57658.7, 57087.8, 59999.9, 56522.5),
        (0.00170016, 0.00171717, 0.00173434, 0.00175168, 0.00167504, 0.0017692),
        ["buy"] * 4 + ["sell"] + ["buy"],
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == side
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    # ==========================================================================
    # 5. FILLING A SELL ORDER
    # Now let's see if the sell order gets triggered.
    await api.on_ticker_update(callback=ws_client.on_message, last=60000.0)
    assert state_machine.state != States.ERROR
    assert strategy._orderbook_table.count() == 5

    for order, price, volume, side in zip(
        strategy._orderbook_table.get_orders().all(),
        (58817.7, 58235.3, 57658.7, 57087.8, 56522.5),
        (0.00170016, 0.00171717, 0.00173434, 0.00175168, 0.0017692),
        ["buy"] * 5,
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == side
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    # ... as we can see, the sell order got removed from the orderbook.
    # ... there is no new corresponding buy order placed - this would only be
    # the case for the case, if there would be more sell orders.
    # As usual, if the price would rise higher, the buy orders would shift up.

    # ==========================================================================
    # 6. RAPID PRICE DROP - FILLING ALL BUY ORDERS
    # Now check the behavior for a rapid price drop.
    await api.on_ticker_update(callback=ws_client.on_message, last=50000.0)
    assert state_machine.state != States.ERROR
    assert strategy._orderbook_table.count() == 5

    for order, price, volume in zip(
        strategy._orderbook_table.get_orders().all(),
        (59405.8, 58817.6, 58235.2, 57658.6, 57087.7),
        (0.00169179, 0.00170871, 0.0017258, 0.00174306, 0.00176049),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == "sell"
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    # ==========================================================================
    # 7. SELL ALL AND ENSURE N OPEN BUY ORDERS
    #    Here we temporarily have more than 5 buy orders, since every sell order
    #    triggers a new buy order, causing us to have 9 buy orders and a single
    #    sell order. Which is not a problem, since the buy orders that are too
    #    much will get canceled after the next price update.
    await api.on_ticker_update(callback=ws_client.on_message, last=59100.0)
    assert state_machine.state != States.ERROR
    assert strategy._orderbook_table.count() == 6
    current_orders = strategy._orderbook_table.get_orders().all()
    assert len(current_orders) == 6

    for order, price, volume in zip(
        (o for o in current_orders if o.side == "sell"),
        (59405.8,),
        (0.00169179,),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == "sell"
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    for order, price, volume in zip(
        (o for o in current_orders if o.side == "buy"),
        (58514.8, 57935.4, 57361.7, 56793.7, 56231.3),
        (0.00170896, 0.00172606, 0.00174332, 0.00176075, 0.00177836),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == "buy"
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    # ==========================================================================
    # 8. MAX INVESTMENT REACHED

    # First ensure that new buy orders can be placed...
    assert not strategy._max_investment_reached
    strategy._GridStrategyBase__cancel_all_open_buy_orders()
    assert strategy._orderbook_table.count() == 1
    await api.on_ticker_update(callback=ws_client.on_message, last=50000.0)
    assert strategy._orderbook_table.count() == 6

    # Now with a different max investment, the max investment should be reached
    # and no further orders be placed.
    assert not strategy._max_investment_reached
    strategy._config.max_investment = 202.0  # 200 USD + fee
    strategy._GridStrategyBase__cancel_all_open_buy_orders()
    assert strategy._orderbook_table.count() == 1
    await api.on_ticker_update(callback=ws_client.on_message, last=50000.0)
    assert strategy._orderbook_table.count() == 2
    assert strategy._max_investment_reached

    assert state_machine.state != States.ERROR


@pytest.mark.integration
@pytest.mark.asyncio
@mock.patch("kraken_infinity_grid.adapters.exchanges.kraken.sleep", return_value=None)
@mock.patch("kraken_infinity_grid.strategies.grid_hodl.sleep", return_value=None)
@mock.patch("kraken_infinity_grid.strategies.grid_base.sleep", return_value=None)
async def test_integration_GridHODL_unfilled_surplus(
    mock_sleep1: mock.MagicMock,  # noqa: ARG001
    mock_sleep2: mock.Mock,  # noqa: ARG001
    mock_sleep3: mock.Mock,  # noqa: ARG001
    kraken_gridhodl_instance: BotEngine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    Integration test for the GridHODL strategy using pre-generated websocket
    messages.

    This test checks if the unfilled surplus is handled correctly.

    unfilled surplus: The base currency volume that was partly filled by an buy
    order, before the order was cancelled.
    """
    caplog.set_level(logging.INFO)

    # Create engine using mocked Kraken API
    engine = kraken_gridhodl_instance
    state_machine = engine._BotEngine__state_machine
    strategy = engine._BotEngine__strategy
    ws_client = strategy._GridHODLStrategy__ws_client
    rest_api = strategy._rest_api
    api = engine._BotEngine__strategy._GridHODLStrategy__ws_client.__websocket_service

    # ==========================================================================
    # During the following processing, the following steps are done:
    # 1. The algorithm prepares for trading (see setup)
    # 2. The order manager checks the price range
    # 3. The order manager checks for n open buy orders
    # 4. The order manager places new orders
    await ws_client.on_message(
        {
            "channel": "executions",
            "type": "snapshot",
            "data": [{"exec_type": "canceled", "order_id": "txid0"}],
        },
    )
    assert state_machine.state != States.ERROR
    assert strategy._ready_to_trade is False

    await api.on_ticker_update(callback=ws_client.on_message, last=50000.0)
    assert strategy._ticker == 50000.0
    assert state_machine.state != States.ERROR
    assert strategy._ready_to_trade is True

    # ==========================================================================
    # 1. PLACEMENT OF INITIAL N BUY ORDERS
    # After both fake-websocket channels are connected, the algorithm went
    # through its full setup and placed orders against the fake Kraken API and
    # finally saved those results into the local orderbook table.

    # Check if the five initial buy orders are placed with the expected price
    # and volume. Note that the interval is not exactly 0.01 due to the fee
    # which is taken into account.
    for order, price, volume in zip(
        strategy._orderbook_table.get_orders().all(),
        (49504.9, 49014.7, 48529.4, 48048.9, 47573.1),
        (0.00202, 0.0020402, 0.0020606, 0.00208121, 0.00210202),
        strict=True,
    ):
        assert order.price == price
        assert order.volume == volume
        assert order.side == "buy"
        assert order.symbol == "BTCUSD"
        assert order.userref == strategy._config.userref

    # ==========================================================================
    # 2. BUYING PARTLY FILLED and ensure that the unfilled surplus is handled

    api.fill_order(strategy._orderbook_table.get_orders().first().txid, 0.002)
    assert strategy._orderbook_table.count() == 5

    balances = api.get_balances()
    assert balances["XXBT"]["balance"] == "100.002"
    assert float(balances["ZUSD"]["balance"]) == pytest.approx(999400.99)

    strategy._handle_cancel_order(
        strategy._orderbook_table.get_orders().first().txid,
    )

    assert strategy._configuration_table.get()["vol_of_unfilled_remaining"] == 0.002
    assert (
        strategy._configuration_table.get()["vol_of_unfilled_remaining_max_price"]
        == 49504.9
    )

    # ==========================================================================
    # 3. SELLING THE UNFILLED SURPLUS
    #    The sell-check is done only during cancelling orders, as this is the
    #    only time where this amount is touched. So we need to create another
    #    partly filled order.

    strategy.new_buy_order(order_price=49504.9)
    assert strategy._orderbook_table.count() == 5
    assert (
        len(
            [
                o
                for o in rest_api.get_open_orders(userref=strategy._config.userref)
                if o.status == "open"
            ]
        )
        == 5
    )

    order = strategy._orderbook_table.get_orders(filters={"price": 49504.9}).all()[0]
    api.fill_order(order["txid"], 0.002)
    strategy._handle_cancel_order(order["txid"])

    assert (
        len(
            [
                o
                for o in rest_api.get_open_orders(userref=strategy._config.userref)
                if o.status == "open"
            ]
        )
        == 5
    )
    assert (
        strategy._configuration_table.get()["vol_of_unfilled_remaining_max_price"]
        == 0.0
    )

    sell_orders = strategy._orderbook_table.get_orders(filters={"side": "sell"}).all()
    assert sell_orders[0].price == 50500.0
    assert sell_orders[0].volume == pytest.approx(0.00199014)
