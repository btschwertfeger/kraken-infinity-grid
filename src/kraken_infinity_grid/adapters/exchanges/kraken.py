# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#
from contextlib import suppress
from decimal import Decimal
from functools import cache
from logging import getLogger
from time import sleep
from typing import Any, Self

from kraken.exceptions import (
    KrakenAuthenticationError,
    KrakenInvalidOrderError,
    KrakenPermissionDeniedError,
)
from kraken.spot import Market, SpotWSClient, Trade, User

from kraken_infinity_grid.core.event_bus import Event, EventBus
from kraken_infinity_grid.core.state_machine import StateMachine, States
from kraken_infinity_grid.exceptions import BotStateError
from kraken_infinity_grid.interfaces.exchange import (
    IExchangeRESTService,
    IExchangeWebSocketService,
)
from kraken_infinity_grid.models.domain import ExchangeDomain

# FIXME: Make pair and symbol uniform
from kraken_infinity_grid.models.schemas.exchange import (
    AssetBalanceSchema,
    AssetPairInfoSchema,
    CreateOrderResponseSchema,
    OrderInfoSchema,
    PairBalanceSchema,
)

LOG = getLogger(__name__)


class KrakenExchangeRESTServiceAdapter(IExchangeRESTService):
    """Adapter for the Kraken exchange user service implementation."""

    def __init__(
        self: Self,
        api_key: str,
        api_secret: str,
        state_machine: StateMachine,
    ) -> None:
        self.__user_service: User = User(key=api_key, secret=api_secret)
        self.__trade_service: Trade = Trade(key=api_key, secret=api_secret)
        self.__market_service: Market = Market()
        self.__state_machine: StateMachine = state_machine

    # == Implemented abstract methods from IExchangeRESTService ================

    def check_api_key_permissions(self: Self) -> None:
        """
        Checks if the credentials are valid and if the API keys have the
        required permissions.
        """
        try:
            LOG.info("- Checking permissions of API keys...")

            LOG.info(" - Checking if 'Query Funds' permission set...")
            self.__user_service.get_account_balance()

            LOG.info(" - Checking if 'Query open order & trades' permission set...")
            self.__user_service.get_open_orders(trades=True)

            LOG.info(" - Checking if 'Query closed order & trades' permission set...")
            self.__user_service.get_closed_orders(trades=True)

            LOG.info(" - Checking if 'Create & modify orders' permission set...")
            self.__trade_service.create_order(
                pair="BTC/USD",
                side="buy",
                ordertype="market",
                volume="10",
                price="10",
                validate=True,
            )
            LOG.info(" - Checking if 'Cancel & close orders' permission set...")
            with suppress(KrakenInvalidOrderError):
                self.__trade_service.cancel_order(
                    txid="",
                    extra_params={"cl_ord_id": "kraken_infinity_grid_internal"},
                )

            LOG.info(" - Checking if 'Websocket interface' permission set...")
            self.__user_service.request(
                method="POST",
                uri="/0/private/GetWebSocketsToken",
            )

            LOG.info(" - Passed API keys and permissions are valid!")
        except (KrakenAuthenticationError, KrakenPermissionDeniedError) as exc:
            self.__state_machine.transition_to(States.ERROR)
            LOG.error(
                (
                    "Passed API keys are invalid!"
                    if isinstance(exc, KrakenAuthenticationError)
                    else "Passed API keys are missing permissions!"
                ),
            )

    def check_exchange_status(self: Self, tries: int = 0) -> None:
        """Checks whether the Kraken API is available."""
        if tries == 3:
            LOG.error("- Could not connect to the Kraken Exchange API.")
            self.__state_machine.transition_to(States.ERROR)
        try:
            if (
                status := self.__market_service.get_system_status().lower()
            ) == "online":
                LOG.info("- Kraken Exchange API Status: Online")
                return
            LOG.warning("- Kraken Exchange API Status: %s", status)
            raise ConnectionError("Kraken API is not online.")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            LOG.debug(
                "Exception while checking Kraken API status: %s",
                exc,
                exc_info=exc,
            )
            LOG.warning("- Kraken not available. (Try %d/3)", tries + 1)
            sleep(3)
            self.check_exchange_status(tries=tries + 1)

    def get_orders_info(self: Self, txid: int = None) -> OrderInfoSchema | None:
        """
        {
            "descr": {"pair": "XBTUSD", "price": "10000.0", "type": "buy"},
            "txid": "O5X7QF-3W5X7Q-3W5X7Q", # added manually
            "userref": 123456,
        }
        """
        if not (order_info := self.__user_service.get_orders_info(txid=txid).get(txid)):
            return None
        return OrderInfoSchema(**order_info, **order_info["descr"], txid=txid)

    def get_open_orders(
        self: Self,
        userref: int = None,
        trades: bool = None,
    ) -> list[OrderInfoSchema]:
        orders = []
        for txid, order in self.__user_service.get_open_orders(
            userref=userref,
            trades=trades,
        )["open"].items():
            orders.append(OrderInfoSchema(**order, **order["descr"], txid=txid))
        return orders

    def get_order_with_retry(
        self: Self,
        txid: str,
        tries: int = 0,
        max_tries: int = 5,
        exit_on_fail: bool = True,
    ) -> dict | None:
        """
        Returns the order details for a given txid.

        NOTE: We need retry here, since Kraken lacks of fast processing of
              placed/filled orders and making them available via REST API.
        """
        while tries < max_tries and not (
            order_details := self.get_orders_info(txid=txid)
        ):
            tries += 1
            LOG.warning(
                "Could not find order '%s'. Retry %d/%d in %d seconds...",
                txid,
                tries,
                max_tries,
                (wait_time := 2 * tries),
            )
            sleep(wait_time)

        if exit_on_fail and order_details is None:
            message = (
                f"Failed to retrieve order info for '{txid}' after {max_tries} retries!"
            )
            LOG.error(message)
            self.__state_machine.transition_to(States.ERROR)
            raise BotStateError(message)

        return order_details  # type: ignore[no-any-return]

    def get_account_balance(self: Self) -> dict[str, float]:
        """
        NOTE: Currently only used during initialization to check if permissions
        are set.
        """
        return self.__user_service.get_account_balance()

    def get_closed_orders(
        self: Self,
        userref: int = None,
        trades: bool = None,
    ) -> dict[str, Any]:
        """
        NOTE: Currently only used during initialization to check if permissions
        are set.
        """
        return self.__user_service.get_closed_orders(userref=userref, trades=trades)

    def get_balances(self: Self) -> list[AssetBalanceSchema]:
        LOG.debug("Retrieving the user's balances...")
        balances = []
        for symbol, data in self.__user_service.get_balances().items():
            balances.append(AssetBalanceSchema(asset=symbol, **data))
        return balances

    def get_pair_balance(
        self: Self,
        base_currency: str,
        quote_currency: str,
    ) -> PairBalanceSchema:
        """
        Returns the available and overall balances of the quote and base
        currency.

        FIXME: Is there a way to get the balances of the asset pair directly?
        """
        custom_base, custom_quote = self.__retrieve_custom_base_quote_names(
            base_currency=base_currency,
            quote_currency=quote_currency,
        )

        base_balance = Decimal(0)
        base_available = Decimal(0)
        quote_balance = Decimal(0)
        quote_available = Decimal(0)

        for balance in self.get_balances():
            if balance.symbol == custom_base:
                base_balance = Decimal(balance.balance)
                base_available = base_balance - Decimal(balance.hold_trade)
            elif balance.symbol == custom_quote:
                quote_balance = Decimal(balance.balance)
                quote_available = quote_balance - Decimal(balance.hold_trade)

        LOG.debug(
            "Retrieved balances: %s",
            balances := PairBalanceSchema(
                base_balance=float(base_balance),
                quote_balance=float(quote_balance),
                base_available=float(base_available),
                quote_available=float(quote_available),
            ),
        )
        return balances

    @cache
    @staticmethod
    def altname(base_currency: str, quote_currency: str) -> str:
        return f"{base_currency}{quote_currency}".upper()

    @cache
    @staticmethod
    def symbol(base_currency: str, quote_currency: str) -> str:
        """Returns the symbol for the given base and quote currency."""
        return f"{base_currency}/{quote_currency}".upper()

    def create_order(
        self: Self,
        ordertype: str,
        side: str,
        volume: float,
        base_currency: str,
        quote_currency: str,
        price: float,
        userref: int,
        validate: bool = False,
        oflags: str | None = None,
    ) -> CreateOrderResponseSchema:
        """Create a new order."""
        return CreateOrderResponseSchema(
            txid=self.__trade_service.create_order(
                ordertype=ordertype,
                side=side,
                volume=volume,
                pair=f"{base_currency}/{quote_currency}",
                price=price,
                userref=userref,
                validate=validate,
                oflags=oflags,
            )["txid"][0],
        )

    def cancel_order(self: Self, txid: str, **kwargs) -> None:
        """Cancel an order."""
        self.__trade_service.cancel_order(txid=txid, **kwargs)

    def truncate(
        self: Self,
        amount: float,
        amount_type: str,
        base_currency: str,
        quote_currency: str,
    ) -> str:
        """Truncate amount according to exchange precision."""
        return self.__trade_service.truncate(
            amount=amount,
            amount_type=amount_type,
            pair=f"{base_currency}/{quote_currency}",
        )

    def get_system_status(self: Self) -> str:
        """Get the current system status of the exchange."""
        return self.__market_service.get_system_status()["status"]

    def get_asset_pair_info(
        self: Self,
        base_currency: str,
        quote_currency: str,
    ) -> AssetPairInfoSchema:
        """Get available asset pair information from the exchange."""
        # FIXME: Proper error handling
        pair = f"{base_currency}/{quote_currency}"
        if (pair_info := self.__market_service.get_asset_pairs(pair=pair)) != {}:
            raise ValueError(
                f"Could not get asset pair info for {pair}. "
                "Please check the pair name and try again.",
            )

        return AssetPairInfoSchema(**next(iter(pair_info)))

    @cache
    def get_exchange_domain(self) -> ExchangeDomain:
        return ExchangeDomain(
            EXCHANGE="Kraken",
            BUY="buy",
            SELL="sell",
            OPEN="open",
            CLOSED="closed",
            CANCELED="canceled",
            EXPIRED="expired",
            PENDING="pending",
        )

    # == Custom Kraken Methods for convenience =================================

    @cache
    def __retrieve_custom_base_quote_names(
        self: Self,
        base_currency: str,
        quote_currency: str,
    ) -> tuple[str, str]:
        """
        Returns the custom base and quote name for the given currencies.
        On Kraken, crypto assets are prefixed with 'X' (e.g., 'XETH', 'XXBT'),
        while fiat assets are prefixed with 'Z' (e.g., 'ZEUR', 'ZUSD').

        This can be cached, since the asset names do not change frequently.
        """
        pair_info: AssetPairInfoSchema = self.get_asset_pair_info(
            base_currency=base_currency,
            quote_currency=quote_currency,
        )
        return pair_info.base, pair_info.quote


class KrakenExchangeWebsocketServiceAdapter(IExchangeWebSocketService):
    """Adapter for the Kraken exchange websocket service implementation."""

    def __init__(
        self: Self,
        api_key: str,
        api_secret: str,
        state_machine: StateMachine,
        event_bus: EventBus,
    ) -> None:
        self.__websocket_service: SpotWSClient = SpotWSClient(
            key=api_key,
            secret=api_secret,
            callback=self.on_message,
        )
        self.__state_machine: StateMachine = state_machine
        self.__event_bus: EventBus = event_bus

        # Store messages received before the algorithm is ready to trade.
        self.__missed_messages = []

    async def start(self: Self) -> None:
        """Start the websocket service."""
        await self.__websocket_service.start()

    async def close(self: Self) -> None:
        """Cancel the websocket service."""
        await self.__websocket_service.close()

    async def subscribe(self: Self, params: dict[str, Any]) -> None:
        """Subscribe to the websocket service."""
        await self.__websocket_service.subscribe(params=params)

    async def on_message(
        self: Self,
        message: dict[str, Any],
        **kwargs: dict[str, Any],
    ) -> None:
        """Handle incoming messages from the websocket."""

        if self.__state_machine.state in {States.SHUTDOWN_REQUESTED, States.ERROR}:
            LOG.debug("Shutdown requested, not processing incoming messages.")
            return

        try:
            # ==================================================================
            # Filtering out unwanted messages
            if not isinstance(message, dict):
                LOG.warning("Message is not a dict: %s", message)
                return

            if (channel := message.get("channel")) in {"heartbeat", "status"}:
                return

            if message.get("method"):
                if message["method"] == "subscribe" and not message["success"]:
                    LOG.error(
                        "The algorithm was not able to subscribe to selected"
                        " channels. Please check the logs.",
                    )
                    self.__state_machine.transition_to(States.ERROR)
                    return
                return

            # ==================================================================
            # Initial setup
            if (
                channel == "ticker"
                and not self.__state_machine.facts["ticker_channel_connected"]
            ):
                self.__state_machine.facts["ticker_channel_connected"] = True
                # Set ticker the first time to have the ticker set during setup.
                self.__event_bus.publish(
                    Event(
                        type="ticker_update",
                        data={"last": float(message["data"][0]["last"])},
                    ),
                )
                LOG.info("- Subscribed to ticker channel successfully!")

            elif (
                channel == "executions"
                and not self.__state_machine.facts["executions_channel_connected"]
            ):
                self.__state_machine.facts["executions_channel_connected"] = True
                LOG.info("- Subscribed to execution channel successfully!")

            if (
                self.__state_machine.facts["ticker_channel_connected"]
                and self.__state_machine.facts["executions_channel_connected"]
                and not self.__state_machine.facts["ready_to_trade"]
            ):
                self.__event_bus.publish(
                    Event(type="prepare_for_trading", data={}),
                )

                # If there are any missed messages, process them now.
                for msg in self.__missed_messages:
                    await self.on_message(msg)
                self.__missed_messages = []

            if not self.__state_machine.facts["ready_to_trade"]:
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

            if channel == "ticker" and (data := message.get("data")):
                self.__event_bus.publish(
                    Event(
                        type="ticker_update",
                        data={"symbol": data[0].get("symbol"), "last": data[0]["last"]},
                    ),
                )

            elif channel == "executions" and (data := message.get("data", [])):
                if message.get("type") == "snapshot":
                    # Snapshot data is not interesting, as this is handled
                    # during sync with upstream.
                    return

                for execution in data:
                    LOG.debug("Got execution: %s", execution)
                    match execution["exec_type"]:
                        case "new":
                            self.__event_bus.publish(
                                Event(
                                    type="on_order_placed",
                                    data={"order_id": execution["order_id"]},
                                ),
                            )
                        case "filled":
                            self.__event_bus.publish(
                                Event(
                                    type="on_order_filled",
                                    data={"order_id": execution["order_id"]},
                                ),
                            )
                        case "canceled" | "expired":
                            self.__event_bus.publish(
                                Event(
                                    type="on_order_cancelled",
                                    data={"order_id": execution["order_id"]},
                                ),
                            )

        except Exception as exc:  # noqa: BLE001
            LOG.error(msg="Exception while processing message.", exc_info=exc)
            self.__state_machine.transition_to(States.ERROR)
            return
