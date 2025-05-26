# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from typing import Any, TYPE_CHECKING
from kraken_infinity_grid.interfaces.interfaces import (
    IExchangeRESTService,
    IExchangeWebsocketService,
    IOrderbookService,
)
from logging import getLogger
from kraken_infinity_grid.core.event_bus import EventBus
from kraken.spot import User, Trade, Market, SpotWSClient
from kraken_infinity_grid.core.state_machine import StateMachine, States
from types import SimpleNamespace
LOG = getLogger(__name__)
from
class KrakenExchangeRESTServiceAdapter(IExchangeRESTService):
    """Adapter for the Kraken exchange user service implementation."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        self._user_service: User = User(key=api_key, secret=api_secret)
        self._trade_service: Trade = Trade(key=api_key, secret=api_secret)
        self._market_service: Market = Market()

    # == Getters for exchange user operations ==================================
    def get_orders_info(self, txid: int = None) -> dict[str, Any]:
        return self._user_service.get_orders_info(txid=txid)

    def get_open_orders(
        self, userref: int = None, trades: bool = None
    ) -> dict[str, Any]:
        return self._user_service.get_open_orders(userref=userref, trades=trades)

    def get_account_balance(self) -> dict[str, float]:
        return self._user_service.get_account_balance()

    def get_closed_orders(
        self, userref: int = None, trades: bool = None
    ) -> dict[str, Any]:
        return self._user_service.get_closed_orders(userref=userref, trades=trades)

    def get_balances(self) -> dict[str, float]:
        return self._user_service.get_balances()

    # == Getters for exchange trade operations =================================
    def create_order(
        self,
        ordertype: str,
        side: str,
        volume: float,
        pair: str,
        price: float,
        userref: int,
        validate: bool = False,
        oflags: str | None = None,
    ) -> dict[str, Any]:
        """Create a new order."""
        return self._trade_service.create_order(
            ordertype=ordertype,
            side=side,
            volume=volume,
            pair=pair,
            price=price,
            userref=userref,
            validate=validate,
            oflags=oflags,
        )

    def cancel_order(self, txid: str) -> dict[str, Any]:
        """Cancel an order."""
        return self._trade_service.cancel_order(txid=txid)

    def truncate(self, amount: float, amount_type: str, pair: str) -> str:
        """Truncate amount according to exchange precision."""
        return self._trade_service.truncate(
            amount=amount, amount_type=amount_type, pair=pair
        )

    # == Getters for exchange market operations ================================
    def get_system_status(self) -> dict[str, Any]:
        """Get the current system status of the exchange."""
        return self._market_service.get_system_status()

    def get_asset_pairs(self, pair: str) -> dict[str, Any]:
        """Get available asset pairs on the exchange."""
        return self._market_service.get_asset_pairs(pair=[pair])


class KrakenExchangeWebsocketServiceAdapter(IExchangeWebsocketService):
    """Adapter for the Kraken exchange websocket service implementation."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        state_machine: StateMachine,
        event_bus: EventBus,
    ) -> None:
        self._websocket_service: SpotWSClient = SpotWSClient(
            key=api_key, secret=api_secret, callback=self.on_message
        )
        self._state_machine: StateMachine = state_machine
        self._event_bus: EventBus = event_bus

    async def start(self) -> None:
        """Start the websocket service."""
        await self._websocket_service.start()

    async def cancel(self) -> None:
        """Cancel the websocket service."""
        await self._websocket_service.cancel()

    async def subscribe(self, params: dict[str, Any]) -> None:
        """Subscribe to the websocket service."""
        await self._websocket_service.subscribe(params=params)

    async def on_message(
        self, message: dict[str, Any], **kwargs: dict[str, Any]
    ) -> None:
        """Handle incoming messages from the websocket."""

        if self._state_machine.state in {States.SHUTDOWN_REQUESTED, States.ERROR}:
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
                    self._state_machine.transition_to(States.ERROR)
                    return
                return

            # ==================================================================
            # Initial setup
            if (
                channel == "ticker"
                and not self._state_machine.facts["ticker_channel_connected"]
            ):
                self._state_machine.facts["ticker_channel_connected"] = True
                # Set ticker the first time to have the ticker set during setup.
                self.ticker = SimpleNamespace(last=float(message["data"][0]["last"]))
                LOG.info("- Subscribed to ticker channel successfully!")

            elif (
                channel == "executions"
                and not self._state_machine.facts["executions_channel_connected"]
            ):
                self._state_machine.facts["executions_channel_connected"] = True
                LOG.info("- Subscribed to execution channel successfully!")

            if (
                self._state_machine.facts["ticker_channel_connected"]
                and self._state_machine.facts["executions_channel_connected"]
                and not self._state_machine.facts["ready_to_trade"]
            ):
                self.sm.prepare_for_trading()

                # If there are any missed messages, process them now.
                for msg in self.__missed_messages:
                    await self.on_message(msg)
                self.__missed_messages = []

            if not self._state_machine.facts["ready_to_trade"]:
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
                self._event_bus.publish("ticker_update", {"last": data[0]["last"]})


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
            self._state_machine.transition_to(States.ERROR)
            return


