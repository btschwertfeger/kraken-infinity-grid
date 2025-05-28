# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

import asyncio
import signal
import sys
from datetime import datetime, timedelta
from importlib.metadata import version
from logging import getLogger
from typing import Any, Self

from kraken_infinity_grid.core.event_bus import EventBus
from kraken_infinity_grid.core.state_machine import StateMachine, States
from kraken_infinity_grid.exceptions import GridBotStateError
from kraken_infinity_grid.infrastructure.database import (
    Configuration,
    DBConnect,
    Orderbook,
    PendingTXIDs,
    UnsoldBuyOrderTXIDs,
)
from kraken_infinity_grid.models.dto.configuration import (
    BotConfigDTO,
    DBConfigDTO,
    NotificationConfigDTO,
)
from kraken_infinity_grid.services.notification_service import NotificationService

LOG = getLogger(__name__)


class Bot:
    """
    Orchestrates the trading bot's components but delegates specific
    responsibilities to specialized classes.
    """

    def __init__(
        self: Self,
        bot_config: BotConfigDTO,
        db_config: DBConfigDTO,
        notification_config: NotificationConfigDTO,
    ) -> None:
        LOG.info(
            "Initiate the Kraken Infinity Grid Algorithm instance (v%s)",
            version("kraken-infinity-grid"),
        )
        LOG.debug("Config: %s", bot_config)

        self.__event_bus = EventBus()
        self.__state_machine = StateMachine()
        self.__config = bot_config
        self.__userref: int = self.__config.userref

        # == Infrastructure components =========================================
        ##
        self.__db = DBConnect(**db_config)
        self.__orderbook_table = Orderbook(userref=self.__userref, db=self.__db)
        self.__configuration_table = Configuration(userref=self.__userref, db=self.__db)
        self.__pending_txids_table = PendingTXIDs(userref=self.__userref, db=self.__db)
        self.__unsold_buy_order_txids_table = UnsoldBuyOrderTXIDs(
            userref=self.__userref,
            db=self.__db,
        )
        self.__db.init_db()

        exchange_services = self.__exchange_factory()
        self.__rest_api = exchange_services["REST"]
        self.__ws_client = exchange_services["websocket"]

        # == Application services ==============================================
        ##
        self.__notification_service = NotificationService(notification_config)

        # Create the appropriate strategy based on config
        self.__strategy = self.__strategy_factory()

        # Setup event subscriptions
        self.__setup_event_handlers()

    def __strategy_factory(self: Self) -> Any:
        from kraken_infinity_grid.strategies.grid import (  # pylint: disable=import-outside-toplevel
            CDCAStrategy,
            GridHodlStrategy,
            GridSellStrategy,
            SwingStrategy,
        )

        if self.__config.strategy not in (
            strategies := {
                "SWING": SwingStrategy,
                "GridHODL": GridHodlStrategy,
                "GridSell": GridSellStrategy,
                "cDCA": CDCAStrategy,
            }
        ):
            raise ValueError(f"Unknown strategy type: {self.__config.strategy}")

        return strategies[self.__config.strategy](
            config=self.__config,
            state_machine=self.__state_machine,
            rest_api=self.__rest_api,
            event_bus=self.__event_bus,
            configuration_table=self.__configuration_table,
            orderbook_table=self.__orderbook_table,
            pending_txids_table=self.__pending_txids_table,
            unsold_buy_order_txids_table=self.__unsold_buy_order_txids_table,
        )

    def __exchange_factory(self: Self) -> dict:
        """Create the exchange service based on the configuration."""
        if self.__config.exchange == "Kraken":
            from kraken_infinity_grid.adapters.exchanges.kraken import (  # pylint: disable=import-outside-toplevel
                KrakenExchangeRESTServiceAdapter,
                KrakenExchangeWebsocketServiceAdapter,
            )

            return {
                "REST": KrakenExchangeRESTServiceAdapter(
                    api_key=self.__config.api_key,
                    api_secret=self.__config.api_secret,
                    state_machine=self.__state_machine,
                ),
                "websocket": KrakenExchangeWebsocketServiceAdapter(
                    api_key=self.__config.api_key,
                    api_secret=self.__config.api_secret,
                    state_machine=self.__state_machine,
                    event_bus=self.__event_bus,
                ),
            }
        raise ValueError(f"Unsupported exchange: {self.__config.exchange}")

    def __setup_event_handlers(self: Self) -> None:
        # Subscribe to events

        # prepare_for_trading is called after the initial setup is done and the
        # websocket connection is established.
        self.__event_bus.subscribe(
            "prepare_for_trading",
            self.__strategy.on_prepare_for_trading,
        )
        self.__event_bus.subscribe("ticker_update", self.__strategy.on_ticker_update)
        self.__event_bus.subscribe("order_placed", self.__strategy.on_order_placed)
        self.__event_bus.subscribe("order_filled", self.__strategy.on_order_filled)
        self.__event_bus.subscribe(
            "order_cancelled",
            self.__strategy.on_order_cancelled,
        )
        self.__event_bus.subscribe(
            "notification",
            self.__notification_service.on_notification,
        )

    async def run(self: Self) -> None:
        """Start the bot"""
        LOG.info("Starting the Kraken Infinity Grid Algorithm...")

        # ======================================================================
        # Handle the shutdown signals
        #
        # A controlled shutdown is initiated by sending a SIGINT or SIGTERM
        # signal to the process. Since requests and database interactions are
        # executed synchronously, we only need to set the stop_event during
        # on_message, ensuring no further messages are processed.
        ##
        def _signal_handler() -> None:
            LOG.warning("Initiate a controlled shutdown of the algorithm...")
            self.__state_machine.transition_to(States.SHUTDOWN_REQUESTED)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

        # ======================================================================
        # Try to connect to the Kraken API, validate credentials and API key
        # permissions.
        ##
        self.__rest_api.check_exchange_status()
        self.__rest_api.check_api_key_permissions()

        if self.__state_machine.state == States.ERROR:
            await self.terminate(
                "The algorithm was shut down by error during initialization!",
            )

        # ======================================================================
        # Start the websocket connection
        ##
        LOG.info("Starting the websocket connection...")
        await self.__ws_client.start()
        LOG.info("Websocket connection established!")

        # ======================================================================
        # Subscribe to the execution and ticker channels
        ##
        LOG.info("Subscribing to channels...")
        subscriptions = {
            "Kraken": [
                {
                    "channel": "ticker",
                    "symbol": [
                        f"{self.__config.base_currency}/{self.__config.quote_currency}",
                    ],
                },
                {
                    "channel": "executions",
                    # Snapshots are only required to check if the channel is
                    # connected. They are not used for any other purpose.
                    "snap_orders": True,
                    "snap_trades": True,
                },
            ],
        }
        for subscription in subscriptions[self.__config["exchange"]]:
            self.__ws_client.subscribe(subscription)

        # Set this initially in case the DB contains a value that is too old.
        self.__configuration_table.update({"last_price_time": datetime.now()})

        # ======================================================================
        # Start the websocket connections and run the main function
        ##
        try:
            # Wait for shutdown
            await asyncio.wait(
                [
                    asyncio.create_task(self.__notification_loop()),
                    asyncio.create_task(self.__state_machine.wait_for_shutdown()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError as exc:
            self.__state_machine.transition_to(States.ERROR)
            await asyncio.sleep(5)
            await self.terminate(f"The algorithm was interrupted: {exc}")
        except (
            GridBotStateError,
            Exception,
        ) as exc:  # pylint: disable=broad-exception-caught
            self.__state_machine.transition_to(States.ERROR)
            await asyncio.sleep(5)
            await self.terminate(f"The algorithm was interrupted by exception: {exc}")

        await asyncio.sleep(5)

        if self.__state_machine.state == States.SHUTDOWN_REQUESTED:
            # The algorithm was interrupted by a signal.
            await self.terminate(
                "The algorithm was shut down successfully!",
                exception=False,
            )
        elif self.__state_machine.state == States.ERROR:
            await self.terminate(
                "The algorithm was shut down due to an error!",
            )

    async def __notification_loop(self: Self) -> None:
        while True:
            try:
                conf = self.__configuration_table.get()
                last_hour = (now := datetime.now()) - timedelta(hours=1)

                if self.__state_machine.state == States.RUNNING and (
                    not conf["last_price_time"]
                    or not conf["last_telegram_update"]
                    or conf["last_telegram_update"] < last_hour
                ):
                    # Send update once per hour to Telegram
                    self.t.send_telegram_update()

                if conf["last_price_time"] + timedelta(seconds=600) < now:
                    # Exit if no price update for a long time (10 minutes).
                    LOG.error("No price update for a long time, exiting!")
                    self.__state_machine.transition_to(States.ERROR)
                    return

            except Exception as exc:  # pylint: disable=broad-exception-caught
                LOG.error("Exception in main.", exc_info=exc)
                self.__state_machine.transition_to(States.ERROR)
                return

            await asyncio.sleep(6)

    async def terminate(
        self: Self,
        reason: str = "",
        *,
        exception: bool = True,
    ) -> None:
        """
        Handle the termination of the algorithm.

        1. Stops the websocket connections and aiohttp sessions managed by the
           python-kraken-sdk
        2. Stops the connection to the database.
        3. Notifies the user via Telegram about the termination.
        4. Exits the algorithm.
        """
        await self.__ws_client.close()
        self.__db.close()

        self.__event_bus.publish(
            "notification",
            {"message": f"{self.__config.name} terminated.\nReason: {reason}"},
        )
        sys.exit(exception)
