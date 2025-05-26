# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from typing import Any
import asyncio
import signal
from kraken_infinity_grid.core.event_bus import EventBus
from kraken_infinity_grid.core.state_machine import StateMachine
from kraken_infinity_grid.infrastructure.database import (
    Configuration,
    DBConnect,
    Orderbook,
    PendingTXIDs,
    UnsoldBuyOrderTXIDs,
)
from kraken_infinity_grid.services import OrderbookService
from kraken_infinity_grid.strategies import (
    CDCAStrategy,
    GridHodlStrategy,
    GridSellStrategy,
    SwingStrategy,
)
from logging import getLogger
from kraken_infinity_grid.core.state_machine import States
from importlib.metadata import version

from typing import Self
import sys
from datetime import datetime, timedelta
LOG = getLogger(__name__)


class InfinityGridBot:
    """
    Orchestrates the trading bot's components but delegates specific
    responsibilities to specialized classes.
    """

    def __init__(self, config: dict, db_config: dict, dry_run: bool = False):
        LOG.info(
            "Initiate the Kraken Infinity Grid Algorithm instance (v%s)",
            version("kraken-infinity-grid"),
        )
        LOG.debug("Config: %s", config)

        self.__event_bus = EventBus()
        self.__state_machine = StateMachine()
        self.__config = config
        self.__userref: int = config["userref"]
        self.dry_run: bool = dry_run

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

        exchange_services = self.__exchange_factory(
            config["exchange"],
            config["api_key"],
            config["api_secret"],
            event_bus=self.__event_bus,
            state_machine=self.__state_machine,
        )
        self.rest_api = exchange_services["REST"]
        self.ws_client = exchange_services["websocket"]

        # == Application services ==============================================
        ##
        self.orderbook_service = OrderbookService(
            config=config,
            rest_api=self.rest_api,
            event_bus=self.__event_bus,
            state_machine=self.__state_machine,
            orderbook_table=self.__orderbook_table,
            pending_txids_table=self.__pending_txids_table,
            unsold_buy_order_txids_table=self.__unsold_buy_order_txids_table,
        )

        # Create the appropriate strategy based on config
        self.strategy = self.__strategy_factory(config, self.__state_machine)

        # Setup event subscriptions
        self.__setup_event_handlers()

    def __strategy_factory(self, config: dict, state_machine: StateMachine) -> Any:
        if (strategy_type := config["strategy"]) not in (
            strategies := {
                "SWING": SwingStrategy,
                "GridHODL": GridHodlStrategy,
                "GridSell": GridSellStrategy,
                "cDCA": CDCAStrategy,
            }
        ):
            raise ValueError(f"Unknown strategy type: {strategy_type}")

        return strategies[strategy_type](
            state_machine=state_machine,
            rest_api=self.rest_api,
            orderbook_service=self.orderbook_service,
            event_bus=self.__event_bus,
        )

    def __exchange_factory(
        self,
        exchange: str,
        api_key: str,
        api_secret: str,
        event_bus: EventBus,
        state_machine: StateMachine,
    ) -> dict:
        """Create the exchange service based on the configuration."""
        if exchange == "Kraken":
            from kraken_infinity_grid.adapters.exchanges.kraken import (  # pylint: disable=import-outside-toplevel
                KrakenExchangeRESTServiceAdapter,
                KrakenExchangeWebsocketServiceAdapter,
            )

            return {
                "REST": KrakenExchangeRESTServiceAdapter(
                    api_key=api_key,
                    api_secret=api_secret,
                ),
                "websocket": KrakenExchangeWebsocketServiceAdapter(
                    api_key=api_key,
                    api_secret=api_secret,
                    state_machine=state_machine,
                    event_bus=event_bus,
                ),
            }
        raise ValueError(f"Unsupported exchange: {exchange}")

    def __setup_event_handlers(self):
        # Subscribe to events
        self.__event_bus.subscribe(
            "prepare_for_trading", self.strategy.prepare_for_trading
        )
        self.__event_bus.subscribe("ticker_update", self.strategy.on_ticker_update)
        self.__event_bus.subscribe("order_placed", self.strategy.on_order_placed)
        self.__event_bus.subscribe("order_filled", self.strategy.on_order_filled)
        self.__event_bus.subscribe("order_cancelled", self.strategy.on_order_cancelled)

    async def run(self):
        """Start the bot"""

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
        # FIXME: API key verification is required here

        # ======================================================================
        # Start the websocket connection
        ##
        LOG.info("Starting the websocket connection...")
        await self.ws_client.start()
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
                        f"{self.__config['base_currency']}/{self.__config['quote_currency']}"
                    ],
                },
                {
                    "channel": "executions",
                    # Snapshots are only required to check if the channel is
                    # connected. They are not used for any other purpose.
                    "snap_orders": True,
                    "snap_trades": True,
                },
            ]
        }
        for subscription in subscriptions[self.__config["exchange"]]:
            self.ws_client.subscribe(subscription)

        # Set this initially in case the DB contains a value that is too old.
        # FIXME: self.configuration.update({"last_price_time": datetime.now()})

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
        except Exception as exc:  # pylint: disable=broad-exception-caught
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

            except (
                Exception  # pylint: disable=broad-exception-caught
            ) as exc:
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
        await self.ws_client.close()
        self.__db.close()

        self.t.send_to_telegram(
            message=f"{self.name}\n{self.symbol} terminated.\nReason: {reason}",
            exception=exception,
        )
        sys.exit(exception)


# """Module that implements the main strategy"""

# import asyncio
# import signal
# import sys
# import traceback
# from contextlib import suppress
# from datetime import datetime, timedelta
# from decimal import Decimal
# from importlib.metadata import version
# from logging import getLogger
# from time import sleep
# from types import SimpleNamespace
# from typing import Iterable, Optional, Self

# from kraken.exceptions import (
#     KrakenAuthenticationError,
#     KrakenInvalidOrderError,
#     KrakenPermissionDeniedError,
# )
# from kraken.spot import Market, SpotWSClient, Trade, User

# from kraken_infinity_grid.infrastructure.database import (
#     Configuration,
#     DBConnect,
#     Orderbook,
#     PendingIXIDs,
#     UnsoldBuyOrderTXIDs,
# )
# from kraken_infinity_grid.order_management import OrderManager
# from kraken_infinity_grid.setup import SetupManager
# from kraken_infinity_grid.core.state_machine import StateMachine, States
# from kraken_infinity_grid.infrastructure.telegram import Telegram

# LOG = getLogger(__name__)


# class KrakenInfinityGridBot(SpotWSClient):
#     """
#     The KrakenInfinityGridBot class implements the infinity grid trading bot
#     strategy.

#     The bot is designed to trade on the Kraken exchange and uses the Kraken API
#     to place orders and fetch information about the current trading pair.

#     All actions are triggered via websocket messages received by the
#     ``on_message`` function, which is a callback function used by the
#     python-kraken-sdk.

#     The algorithm manages its orders in an orderbook, configuration, and pending
#     transactions in separate tables in a SQL-based database (PostgreSQL). It
#     uses the passed ``userref`` to distinguish between different instances.
#     E.g.: For one instance of the algorithm one uses the userref 1680953420 for
#     the DOT/USD pair, and 1680953421 for the BTC/USD pair.

#     The available strategies are documented in the README.md file of this
#     project.

#     Internal
#     ========

#     The following steps are a rough description of the internal workflow of the
#     algorithm.

#     Initialization:

#     - This class is derived from the python-kraken-sdk's websocket client, which
#       allows for subscribing to channels and receiving messages. During the
#       init, the algorithm will establish the connection to the database as well
#       as initializing the user, trade, and market clients.
#     - The after the bot is created, events that came from subscribed websocket
#       feeds will trigger the ``on_message`` function. Subscribed feeds are the
#       ticker (of the asset pair) and execution (for order execution updates).
#     - If both channels are connected, the algorithm does an initial setup:
#         - Check pre-conditions
#         - Validate the configuration
#         - Retrieve information about the trading pair (fee, min order size,
#           etc.)
#         - Check, update, and sync the local orderbook with upstream while
#           recovering orders that might not yet found their way into the
#           orderbook after placing.
#         - If there are executed buy orders during downtime, the corresponding
#           sell orders will be placed (depending on the strategy in use).
#         - If all of these are done, the bot is ready to handle new incoming
#           messages.

#     New ticker message:

#     - If the init is not done yet, the algorithm ignores the message.
#     - The ticker will be updated.
#     - The missing sell orders will be assigned (if any). This is done at this
#       place in order to have a frequent check for missing sell orders.
#     - The ``check_price_range`` function will be triggered.
#         - This either calls ``assign_all_pending_txids`` to add orders that were
#           placed but are not yet added to the local orderbook.
#         - Or checks the current price range. The price range check is skipped in
#           case of pending transactions to avoid double orders.
#             - Ensure the existence $n$ open buy orders.
#             - Cancel the lowest buy order if more than $n$ buy orders are open.
#             - Shift-up buy orders if price rises to high.
#                 - Cancel all open buy orders
#                 - Calls ``check_price_range``
#             - If strategy==SWING: Place sell orders if possible

#     New execution message - new order:

#     - If the init is not done yet, the algorithm ignores the message.
#     - The algorithm ties to assign the new order to the orderbook. In some cases
#       this fails, as newly placed orders may not be fetchable via REST API for
#       some time. For this reason, there are some retries implemented.

#     New execution message - filled order:

#     - If the init is not done yet, the algorithm ignores the message.
#     - If the filled order was a buy order (depending on the strategy), the
#       algorithm places a sell order and updates the local orderbook.
#     - If the filled order was a sell order (depending on the strategy), the
#       algorithm places a buy order and updates the local orderbook.

#     New execution message - cancelled order:

#     - If the init is not done yet, the algorithm ignores the message.
#     - The algorithm removes the order from the local orderbook and ensures that
#       in case of a partly filled order, the remaining volume is saved and placed
#       as sell order somewhen later (if it was a buy order). Sell orders usually
#       don't get cancelled.

#     """

#     def __init__(  # pylint: disable=too-many-arguments
#         self: Self,
#         key: str,
#         secret: str,
#         config: dict,
#         db_config: dict,
#         dry_run: bool = False,
#     ) -> None:
#         super().__init__(key=key, secret=secret)

#         LOG.info(
#             "Initiate the Kraken Infinity Grid Algorithm instance (v%s)",
#             version("kraken-infinity-grid"),
#         )
#         LOG.debug("Config: %s", config)

#         self.dry_run: bool = dry_run

#         self.state_machine = StateMachine(initial_state=States.INITIALIZING)
#         self.__stop_event: asyncio.Event = asyncio.Event()
#         self.state_machine.register_callback(
#             States.SHUTDOWN_REQUESTED,
#             self.__stop_event.set,
#         )
#         self.state_machine.register_callback(
#             States.ERROR,
#             self.__stop_event.set,
#         )

#         # Settings and config collection
#         ##
#         self.strategy: str = config["strategy"]
#         self.userref: int = config["userref"]
#         self.name: str = config["name"]

#         # Commonly used config values
#         ##
#         self.interval: float = float(config["interval"])
#         self.amount_per_grid: float = float(config["amount_per_grid"])
#         self.amount_per_grid_plus_fee: float | None = config.get("fee")

#         self.ticker: SimpleNamespace = None
#         self.max_investment: float = config["max_investment"]
#         self.n_open_buy_orders: int = config["n_open_buy_orders"]
#         self.fee: float | None = config.get("fee")
#         self.base_currency: str = config["base_currency"]
#         self.quote_currency: str = config["quote_currency"]

#         self.symbol: str = self.base_currency + "/" + self.quote_currency  # BTC/EUR
#         self.xsymbol: str | None = None  # XXBTZEUR
#         self.altname: str | None = None  # XBTEUR
#         self.zbase_currency: str | None = None  # XXBT
#         self.xquote_currency: str | None = None  # ZEUR
#         self.cost_decimals: int | None = None  # 5 for EUR, i.e., 0.00001 EUR

#         # If the algorithm receives execution messages before being ready to
#         # trade, they will be stored here and processed later.
#         ##
#         self.__missed_messages: list[dict] = []

#         # Define the Kraken clients
#         ##
#         self.user: User = User(key=key, secret=secret)
#         self.market: Market = Market(key=key, secret=secret)
#         self.trade: Trade = Trade(key=key, secret=secret)

#         # Database setup
#         ##
#         self.database: DBConnect = DBConnect(**db_config)
#         self.orderbook: Orderbook = Orderbook(userref=self.userref, db=self.database)
#         self.configuration: Configuration = Configuration(
#             userref=self.userref,
#             db=self.database,
#         )
#         self.pending_txids: PendingIXIDs = PendingIXIDs(
#             userref=self.userref,
#             db=self.database,
#         )
#         self.unsold_buy_order_txids: UnsoldBuyOrderTXIDs = UnsoldBuyOrderTXIDs(
#             userref=self.userref,
#             db=self.database,
#         )
#         self.database.init_db()

#         # Instantiate the algorithm's components
#         ##
#         self.om = OrderManager(strategy=self)
#         self.sm = SetupManager(strategy=self)
#         self.t = Telegram(
#             strategy=self,
#             telegram_token=config["telegram_token"],
#             telegram_chat_id=config["telegram_chat_id"],
#             exception_token=config["exception_token"],
#             exception_chat_id=config["exception_chat_id"],
#         )

#     # ==========================================================================

#     async def run(self: Self) -> None:
#         """
#         Main function that starts the algorithm and runs it until it is
#         interrupted.
#         """
#         LOG.info("Starting the Kraken Infinity Grid Algorithm...")

#         # ======================================================================
#         # Try to connect to the Kraken API, validate credentials and API key
#         # permissions.
#         ##
#         self.__check_kraken_status()

#         try:
#             self.__check_api_keys()
#         except (KrakenAuthenticationError, KrakenPermissionDeniedError) as exc:
#             await self.terminate(
#                 (
#                     "Passed API keys are invalid!"
#                     if isinstance(exc, KrakenAuthenticationError)
#                     else "Passed API keys are missing permissions!"
#                 ),
#             )

#         # ======================================================================
#         # Handle the shutdown signals
#         #
#         # A controlled shutdown is initiated by sending a SIGINT or SIGTERM
#         # signal to the process. Since requests and database interactions are
#         # executed synchronously, we only need to set the stop_event during
#         # on_message, ensuring no further messages are processed.
#         ##
#         def _signal_handler() -> None:
#             LOG.warning("Initiate a controlled shutdown of the algorithm...")
#             self.state_machine.transition_to(States.SHUTDOWN_REQUESTED)

#         loop = asyncio.get_running_loop()
#         for sig in (signal.SIGINT, signal.SIGTERM):
#             loop.add_signal_handler(sig, _signal_handler)

#         # ======================================================================
#         # Start the websocket connections and run the main function
#         ##
#         try:
#             await asyncio.wait(
#                 [
#                     asyncio.create_task(self.__main()),
#                     asyncio.create_task(self.__stop_event.wait()),
#                 ],
#                 return_when=asyncio.FIRST_COMPLETED,
#             )
#         except asyncio.CancelledError as exc:
#             self.state_machine.transition_to(States.ERROR)
#             await asyncio.sleep(5)
#             await self.terminate(f"The algorithm was interrupted: {exc}")
#         except (
#             Exception  # pylint: disable=broad-exception-caught
#         ) as exc:
#             self.state_machine.transition_to(States.ERROR)
#             await asyncio.sleep(5)
#             await self.terminate(f"The algorithm was interrupted by exception: {exc}")

#         await asyncio.sleep(5)

#         if self.state_machine.state == States.SHUTDOWN_REQUESTED:
#             # The algorithm was interrupted by a signal.
#             await self.terminate(
#                 "The algorithm was shut down successfully!",
#                 exception=False,
#             )
#         elif self.state_machine.state == States.ERROR:
#             await self.terminate(
#                 "The algorithm was shut down due to an error!",
#             )


#     def __check_kraken_status(self: Self, tries: int = 0) -> None:
#         """Checks whether the Kraken API is available."""
#         if tries == 3:
#             LOG.error("- Could not connect to the Kraken Exchange API.")
#             sys.exit(1)
#         try:
#             self.market.get_system_status()
#             LOG.info("- Kraken Exchange API Status: Available")
#         except (
#             Exception  # pylint: disable=broad-exception-caught
#         ) as exc:
#             LOG.debug(
#                 "Exception while checking Kraken availability {exc} {traceback}",
#                 extra={"exc": exc, "traceback": traceback.format_exc()},
#             )
#             LOG.warning("- Kraken not available. (Try %d/3)", tries + 1)
#             sleep(3)
#             self.__check_kraken_status(tries=tries + 1)

#     def __check_api_keys(self: Self) -> None:
#         """
#         Checks if the credentials are valid and if the API keys have the
#         required permissions.
#         """
#         LOG.info("- Checking permissions of API keys...")

#         LOG.info(" - Checking if 'Query Funds' permission set...")
#         self.user.get_account_balance()

#         LOG.info(" - Checking if 'Query open order & trades' permission set...")
#         self.user.get_open_orders(trades=True)

#         LOG.info(" - Checking if 'Query closed order & trades' permission set...")
#         self.user.get_closed_orders(trades=True)

#         LOG.info(" - Checking if 'Create & modify orders' permission set...")
#         self.trade.create_order(
#             pair="BTC/USD",
#             side="buy",
#             ordertype="market",
#             volume="10",
#             price="10",
#             validate=True,
#         )
#         LOG.info(" - Checking if 'Cancel & close orders' permission set...")
#         with suppress(KrakenInvalidOrderError):
#             self.trade.cancel_order(
#                 txid="",
#                 extra_params={"cl_ord_id": "kraken_infinity_grid_internal"},
#             )

#         LOG.info(" - Checking if 'Websocket interface' permission set...")
#         self.trade.request(
#             method="POST",
#             uri="/0/private/GetWebSocketsToken",
#         )

#         LOG.info(" - Passed API keys and permissions are valid!")

#     # ======================================================================
#     # Helper Functions
#     ##
