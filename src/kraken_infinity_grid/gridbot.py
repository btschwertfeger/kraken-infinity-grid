#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Module that implements the main strategy"""

import asyncio
import sys
import traceback
from contextlib import suppress
from datetime import datetime, timedelta
from decimal import Decimal
from importlib.metadata import version
from logging import getLogger
from time import sleep
from types import SimpleNamespace
from typing import Iterable, Optional, Self

from kraken.exceptions import (
    KrakenAuthenticationError,
    KrakenInvalidOrderError,
    KrakenPermissionDeniedError,
)
from kraken.spot import Market, SpotWSClient, Trade, User

from kraken_infinity_grid.database import (
    Configuration,
    DBConnect,
    Orderbook,
    PendingIXIDs,
    UnsoldBuyOrderTXIDs,
)
from kraken_infinity_grid.order_management import OrderManager
from kraken_infinity_grid.setup import SetupManager
from kraken_infinity_grid.telegram import Telegram

LOG = getLogger(__name__)


class KrakenInfinityGridBot(SpotWSClient):
    """
    The KrakenInfinityGridBot class implements the infinity grid trading bot
    strategy.

    The bot is designed to trade on the Kraken exchange and uses the Kraken API
    to place orders and fetch information about the current trading pair.

    All actions are triggered via websocket messages received by the
    ``on_message`` function, which is a callback function used by the
    python-kraken-sdk.

    The algorithm manages its orders in an orderbook, configuration, and pending
    transactions in separate tables in a SQL-based database (PostgreSQL). It
    uses the passed ``userref`` to distinguish between different instances.
    E.g.: For one instance of the algorithm one uses the userref 1680953420 for
    the DOT/USD pair, and 1680953421 for the BTC/USD pair.

    The available strategies are documented in the README.md file of this
    project.

    Internal
    ========

    The following steps are a rough description of the internal workflow of the
    algorithm.

    Initialization:

    - This class is derived from the python-kraken-sdk's websocket client, which
      allows for subscribing to channels and receiving messages. During the
      init, the algorithm will establish the connection to the database as well
      as initializing the user, trade, and market clients.
    - The after the bot is created, events that came from subscribed websocket
      feeds will trigger the ``on_message`` function. Subscribed feeds are the
      ticker (of the asset pair) and execution (for order execution updates).
    - If both channels are connected, the algorithm does an initial setup:
        - Check pre-conditions
        - Validate the configuration
        - Retrieve information about the trading pair (fee, min order size,
          etc.)
        - Check, update, and sync the local orderbook with upstream while
          recovering orders that might not yet found their way into the
          orderbook after placing.
        - If there are executed buy orders during downtime, the corresponding
          sell orders will be placed (depending on the strategy in use).
        - If all of these are done, the bot is ready to handle new incoming
          messages.

    New ticker message:

    - If the init is not done yet, the algorithm ignores the message.
    - The ticker will be updated.
    - The missing sell orders will be assigned (if any). This is done at this
      place in order to have a frequent check for missing sell orders.
    - The ``check_price_range`` function will be triggered.
        - This either calls ``assign_all_pending_txids`` to add orders that were
          placed but are not yet added to the local orderbook.
        - Or checks the current price range. The price range check is skipped in
          case of pending transactions to avoid double orders.
            - Ensure the existence $n$ open buy orders.
            - Cancel the lowest buy order if more than $n$ buy orders are open.
            - Shift-up buy orders if price rises to high.
                - Cancel all open buy orders
                - Calls ``check_price_range``
            - If strategy==SWING: Place sell orders if possible

    New execution message - new order:

    - If the init is not done yet, the algorithm ignores the message.
    - The algorithm ties to assign the new order to the orderbook. In some cases
      this fails, as newly placed orders may not be fetchable via REST API for
      some time. For this reason, there are some retries implemented.

    New execution message - filled order:

    - If the init is not done yet, the algorithm ignores the message.
    - If the filled order was a buy order (depending on the strategy), the
      algorithm places a sell order and updates the local orderbook.
    - If the filled order was a sell order (depending on the strategy), the
      algorithm places a buy order and updates the local orderbook.

    New execution message - cancelled order:

    - If the init is not done yet, the algorithm ignores the message.
    - The algorithm removes the order from the local orderbook and ensures that
      in case of a partly filled order, the remaining volume is saved and placed
      as sell order somewhen later (if it was a buy order). Sell orders usually
      don't get cancelled.

    """

    def __init__(  # pylint: disable=too-many-arguments
        self: Self,
        key: str,
        secret: str,
        config: dict,
        db_config: dict,
        dry_run: bool = False,
    ) -> None:
        super().__init__(key=key, secret=secret)

        LOG.info(
            "Initiate the Kraken Infinity Grid Algorithm instance (v%s)",
            version("kraken-infinity-grid"),
        )
        LOG.debug("Config: %s", config)
        self.init_done: bool = False
        self.dry_run: bool = dry_run

        # Settings and config collection
        ##
        self.strategy: str = config["strategy"]
        self.userref: int = config["userref"]
        self.name: str = config["name"]

        # Commonly used config values
        ##
        self.interval: float = float(config["interval"])
        self.amount_per_grid: float = float(config["amount_per_grid"])

        self.amount_per_grid_plus_fee: float | None = config.get("fee")

        self.max_investment: float = config["max_investment"]
        self.n_open_buy_orders: int = config["n_open_buy_orders"]
        self.fee: float | None = None
        self.base_currency: str = config["base_currency"]
        self.quote_currency: str = config["quote_currency"]

        self.symbol: str = self.base_currency + "/" + self.quote_currency  # BTC/EUR
        self.xsymbol: str | None = None  # XXBTZEUR
        self.altname: str | None = None  # XBTEUR
        self.zbase_currency: str | None = None  # XXBT
        self.xquote_currency: str | None = None  # ZEUR
        self.cost_decimals: int | None = None  # 5 for EUR, i.e., 0.00001 EUR

        # If the algorithm receives execution messages before being ready to
        # trade, they will be stored here and processed later.
        ##
        self.__missed_messages: list[dict] = []

        # Wait for ticker to be connected before do some action
        ##
        self.__ticker_channel_connected: bool = False
        self.ticker: SimpleNamespace = None

        self.is_ready_to_trade: bool = False
        self.__execution_channel_connected: bool = False

        # Define the Kraken clients
        ##
        self.user: User = User(key=key, secret=secret)
        self.market: Market = Market(key=key, secret=secret)
        self.trade: Trade = Trade(key=key, secret=secret)

        # Instantiate the algorithm's components
        ##
        self.om = OrderManager(strategy=self)
        self.sm = SetupManager(strategy=self)
        self.t = Telegram(
            strategy=self,
            telegram_token=config["telegram_token"],
            telegram_chat_id=config["telegram_chat_id"],
            exception_token=config["exception_token"],
            exception_chat_id=config["exception_chat_id"],
        )

        # Database setup
        ##
        self.database: DBConnect = DBConnect(**db_config)
        self.orderbook: Orderbook = Orderbook(userref=self.userref, db=self.database)
        self.configuration: Configuration = Configuration(
            userref=self.userref,
            db=self.database,
        )
        self.pending_txids: PendingIXIDs = PendingIXIDs(
            userref=self.userref,
            db=self.database,
        )
        self.unsold_buy_order_txids: UnsoldBuyOrderTXIDs = UnsoldBuyOrderTXIDs(
            userref=self.userref,
            db=self.database,
        )
        self.database.init_db()

    async def on_message(  # noqa: C901, PLR0912
        self: Self,
        message: dict | list,
    ) -> None:
        """
        This function receives all messages that are sent via the websocket
        connections by Kraken. It's the entrypoint of the incoming messages and
        calls the appropriate functions to handle the messages.
        """
        try:
            # =====================================================================
            # Filtering out unwanted messages
            if not isinstance(message, dict):
                LOG.warning("Message is not a dict: %s", message)
                return

            if (channel := message.get("channel")) in {"heartbeat", "status"}:
                return

            if message.get("method"):
                if message["method"] == "subscribe" and not message["success"]:
                    self.save_exit(
                        "The algorithm was not able to subscribe to selected"
                        " channels. Please check the logs.",
                    )
                return

            # =====================================================================
            # Initial setup
            if channel == "ticker" and not self.__ticker_channel_connected:
                self.__ticker_channel_connected = True
                # Set ticker the first time to have the ticker set during setup.
                self.ticker = SimpleNamespace(last=float(message["data"][0]["last"]))
                LOG.info("- Subscribed to ticker channel successfully!")

            elif channel == "executions" and not self.__execution_channel_connected:
                self.__execution_channel_connected = True
                LOG.info("- Subscribed to execution channel successfully!")

            if (
                self.__ticker_channel_connected
                and self.__execution_channel_connected
                and not self.is_ready_to_trade
            ):
                # Sets self.is_ready_to_trade to True
                self.sm.prepare_for_trading()

                # If there are any missed messages, process them now.
                for msg in self.__missed_messages:
                    await self.on_message(msg)
                self.__missed_messages = []

            if not self.is_ready_to_trade:
                if channel == "executions":
                    # If the algorithm is not ready to trade, store the
                    # executions to process them later.
                    self.__missed_messages.append(message)

                # Return here, until the algorithm is ready to trade. It is
                # ready when the init/setup is done and the orderbook is
                # updated.
                return

            # =====================================================================
            # Handle ticker and execution messages

            if (
                channel == "ticker"
                and (data := message.get("data"))
                and data[0].get("symbol") == self.symbol
            ):
                self.configuration.update({"last_price_time": datetime.now()})

                self.ticker = SimpleNamespace(last=float(data[0]["last"]))
                if self.unsold_buy_order_txids.count() != 0:
                    self.om.add_missed_sell_orders()

                self.om.check_price_range()

            elif channel == "executions" and (data := message.get("data", [])):
                if message.get("type") == "snapshot":
                    # Snapshot data is not interesting, as this is handled
                    # during sync with upstream.
                    return

                for execution in data:
                    LOG.debug("Got execution: %s", execution)
                    match execution["exec_type"]:
                        case "new":
                            self.om.assign_order_by_txid(execution["order_id"])
                        case "filled":
                            self.om.handle_filled_order_event(execution["order_id"])
                        case "canceled" | "expired":
                            self.om.handle_cancel_order(execution["order_id"])

        except Exception as exc:  # noqa: BLE001
            LOG.error(msg="Exception while processing message.", exc_info=exc)
            self.save_exit(reason=traceback.format_exc())

    # ==========================================================================

    async def run(self: Self) -> None:
        """
        Main function that starts the algorithm and runs it until it is
        interrupted.
        """
        LOG.info("Starting the Kraken Infinity Grid Algorithm...")

        # ======================================================================
        # Try to connect to the Kraken API, validate credentials and API key
        # permissions.
        ##
        self.__check_kraken_status()

        try:
            self.__check_api_keys()
        except (KrakenAuthenticationError, KrakenPermissionDeniedError) as exc:
            await self.stop()  # Stops the websocket connections
            await self.async_close()  # Stops the aiohttp session
            self.save_exit(
                (
                    "Passed API keys are invalid!"
                    if isinstance(exc, KrakenAuthenticationError)
                    else "Passed API keys are missing permissions!"
                ),
            )

        # ======================================================================
        # Start the websocket connections and run the main function
        ##
        try:
            await self.__main()
        except asyncio.CancelledError:
            await self.stop()  # Stops the websocket connections
            await self.async_close()  # Stops the aiohttp session
            self.save_exit("The algorithm was interrupted!")

    async def __main(self: Self) -> None:
        """
        Main function that runs the algorithm. It subscribes to the ticker and
        execution channels and runs the main loop until the algorithm is
        interrupted.
        """

        # ======================================================================
        # Start the websocket connection
        ##
        LOG.info("Starting the websocket connection...")
        await self.start()
        LOG.info("Websocket connection established!")

        # ======================================================================
        # Subscribe to the execution and ticker channels
        ##
        LOG.info("Subscribing to channels...")
        await self.subscribe(
            params={
                "channel": "ticker",
                "symbol": [f"{self.base_currency}/{self.quote_currency}"],
            },
        )
        await self.subscribe(
            {
                "channel": "executions",
                # Snapshots are only required to check if the channel is
                # connected. They are not used for any other purpose.
                "snap_orders": True,
                "snap_trades": True,
            },
        )

        # Set this initially in case the DB contains a value that is too old.
        self.configuration.update({"last_price_time": datetime.now()})

        # ======================================================================
        # Main Loop: Run until interruption
        ##
        # 'self.exception_occur' is how the python-kraken-sdk notifies about
        # exceptions in the websocket connection.
        while not self.exception_occur:
            try:
                conf = self.configuration.get()
                now = datetime.now()
                last_hour = now - timedelta(hours=1)

                if self.init_done and (
                    not conf["last_price_time"]
                    or not conf["last_telegram_update"]
                    or conf["last_telegram_update"] < last_hour
                ):
                    # Send update once per hour to Telegram
                    self.t.send_bot_update()

                if conf["last_price_time"] + timedelta(seconds=600) < now:
                    # Exit if no price update for a long time (10 minutes).
                    self.save_exit(
                        reason="No price update for a long time, exit!",
                    )

            except (
                Exception  # pylint: disable=broad-exception-caught # noqa: BLE001
            ) as exc:
                self.save_exit(
                    reason=f"Exception in main: {exc} {traceback.format_exc()}",
                )

            await asyncio.sleep(6)

        self.save_exit(
            reason="The websocket connection encountered an exception!",
        )

    def save_exit(self: Self, reason: str = "") -> None:
        """Save exit triggered, saving data and exit the program."""
        message: str = str(
            f"❌ {self.name} ❌"
            f"\n{self.symbol} Save exit triggered, saving data."
            f"\nReason: {reason}",
        )

        try:
            self.t.send_to_telegram(message=message, exception=True)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("%s", message)
            LOG.error("FIXME: look at this: %s: %s", exc, traceback.format_exc())

        sys.exit(1)

    def __check_kraken_status(self: Self, tries: int = 0) -> None:
        """Checks whether the Kraken API is available."""
        if tries == 3:
            LOG.error("- Could not connect to the Kraken Exchange API.")
            sys.exit(1)
        try:
            self.market.get_system_status()
            LOG.info("- Kraken Exchange API Status: Available")
        except (
            Exception  # pylint: disable=broad-exception-caught # noqa: BLE001
        ) as exc:
            LOG.debug(
                "Exception while checking Kraken availability {exc} {traceback}",
                extra={"exc": exc, "traceback": traceback.format_exc()},
            )
            LOG.warning("- Kraken not available. (Try %d/3)", tries + 1)
            sleep(3)
            self.__check_kraken_status(tries=tries + 1)

    def __check_api_keys(self: Self) -> None:
        """
        Checks if the credentials are valid and if the API keys have the
        required permissions.
        """
        LOG.info("- Checking permissions of API keys...")

        LOG.info(" - Checking if 'Query Funds' permission set...")
        self.user.get_account_balance()

        LOG.info(" - Checking if 'Query open order & trades' permission set...")
        self.user.get_open_orders(trades=True)

        LOG.info(" - Checking if 'Query closed order & trades' permission set...")
        self.user.get_closed_orders(trades=True)

        LOG.info(" - Checking if 'Create & modify orders' permission set...")
        self.trade.create_order(
            pair=self.symbol,
            side="buy",
            ordertype="market",
            volume="0.0001",
            price="1",
            validate=True,
        )
        LOG.info(" - Checking if 'Cancel & close orders' permission set...")
        with suppress(KrakenInvalidOrderError):
            self.trade.cancel_order(
                txid="",
                extra_params={"cl_ord_id": "kraken_infinity_grid_internal"},
            )

        LOG.info(" - Checking if 'Websocket interface' permission set...")
        self.trade.request(
            method="POST",
            uri="/0/private/GetWebSocketsToken",
        )

        LOG.info(" - Passed API keys and permissions are valid!")

    # ======================================================================
    # Helper Functions
    ##
    def get_balances(self: Self) -> dict[str, float]:
        """
        Returns the available and overall balances of the quote and base
        currency.
        """
        LOG.debug("Retrieving the user's balances...")

        base_balance: Decimal = Decimal(0)
        base_available: Decimal = Decimal(0)
        quote_balance: Decimal = Decimal(0)
        quote_available: Decimal = Decimal(0)

        for symbol, data in self.user.get_balances().items():
            if symbol == self.zbase_currency:
                base_balance = Decimal(data["balance"])
                base_available = base_balance - Decimal(data["hold_trade"])
            elif symbol == self.xquote_currency:
                quote_balance = Decimal(data["balance"])
                quote_available = quote_balance - Decimal(data["hold_trade"])

        balances = {
            "base_balance": float(base_balance),
            "quote_balance": float(quote_balance),
            "base_available": float(base_available),
            "quote_available": float(quote_available),
        }
        LOG.debug("Retrieved balances: %s", balances)
        return balances

    def get_current_buy_prices(self: Self) -> Iterable[float]:
        """Returns a generator of the prices of open buy orders."""
        LOG.debug("Getting current buy prices...")
        for order in self.orderbook.get_orders(filters={"side": "buy"}):
            yield order["price"]

    def get_order_price(
        self: Self,
        side: str,
        last_price: float,
        extra_sell: Optional[bool] = False,
    ) -> float:
        """
        Returns the order price depending on the strategy and side. Also assigns
        a new highest buy price to configuration if there was a new highest
        buy.
        """
        LOG.debug("Computing the order price...")
        order_price: float
        price_of_highest_buy = self.configuration.get()["price_of_highest_buy"]
        last_price = float(last_price)

        if side == "sell":  # New order is a sell
            if self.strategy == "SWING" and extra_sell:
                # Extra sell order when SWING
                # 2x interval above [last close price | price of highest buy]
                order_price = last_price * (1 + self.interval) * (1 + self.interval)
                if order_price < price_of_highest_buy:
                    order_price = (
                        price_of_highest_buy * (1 + self.interval) * (1 + self.interval)
                    )

            else:
                # Regular sell order (even for SWING) (cDCA will trigger this
                # but it will be filtered out later)
                if last_price > price_of_highest_buy:
                    self.configuration.update(
                        {"price_of_highest_buy": last_price},
                    )

                # Sell price 1x interval above buy price
                order_price = last_price * (1 + self.interval)
                if self.ticker.last > order_price:
                    order_price = self.ticker.last * (1 + self.interval)
            return order_price

        if side == "buy":  # New order is a buy
            order_price = last_price * 100 / (100 + 100 * self.interval)
            if order_price > self.ticker.last:
                order_price = self.ticker.last * 100 / (100 + 100 * self.interval)
            return order_price

        raise ValueError(f"Unknown side: {side}!")

    def get_value_of_orders(self: Self, orders: Iterable) -> float:
        """Returns the overall invested quote that is invested"""
        LOG.debug("Getting value of open orders...")
        investment = sum(
            float(order["price"]) * float(order["volume"]) for order in orders
        )
        LOG.debug("Value of open orders: %d %s", investment, self.quote_currency)
        return investment

    @property
    def investment(self: Self) -> float:
        """Returns the current investment based on open orders."""
        return self.get_value_of_orders(
            orders=self.orderbook.get_orders(),
        )

    @property
    def max_investment_reached(self: Self) -> bool:
        """Returns True if the maximum investment is reached."""
        return (
            self.max_investment <= self.investment + self.amount_per_grid_plus_fee
        ) or (self.max_investment <= self.investment)
