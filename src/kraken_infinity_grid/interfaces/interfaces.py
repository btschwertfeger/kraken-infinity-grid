# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

"""
Interfaces for the Infinity Grid Bot

FIXME: Add comprehensive examples and documentation for each method.
"""

from abc import ABC, abstractmethod
from typing import Any

from kraken_infinity_grid.core.event_bus import EventBus
from kraken_infinity_grid.core.state_machine import StateMachine
from kraken_infinity_grid.infrastructure.database import (
    Orderbook,
    PendingTxids,
    UnsoldBuyOrderTxids,
    Configuration,
)
from kraken_infinity_grid.core.event_bus import Event


class IExchangeRESTService(ABC):
    """Interface for exchange operations."""

    # == Getters for exchange user operations ==================================
    @abstractmethod
    def get_orders_info(self, txid: str | None) -> dict[str, Any]:
        """Get information about the user on the exchange."""

    @abstractmethod
    def get_open_orders(self, userref: int, trades: bool = None) -> dict[str, Any]:
        """Get all open orders for a userref."""

    @abstractmethod
    def get_account_balance(self) -> dict[str, float]:
        """Get the current account balance."""

    @abstractmethod
    def get_closed_orders(
        self,
        userref: int,
        trades: bool,
    ) -> dict[str, Any]:
        """Get closed orders for a userref with an optional limit."""

    @abstractmethod
    def get_balances(self) -> dict[str, float]:
        """Get current balances."""

    # == Getters for exchange trade operations =================================
    @abstractmethod
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

    @abstractmethod
    def cancel_order(self, txid: str) -> dict[str, Any]:
        """Cancel an order."""

    @abstractmethod
    def truncate(self, amount: float, amount_type: str, pair: str) -> str:
        """Truncate amount according to exchange precision."""

    # == Getters for exchange market operations ================================
    @abstractmethod
    def get_system_status(self) -> dict[str, Any]:
        """Get the current system status of the exchange."""

    @abstractmethod
    def get_asset_pairs(self, pair: list[str]) -> dict[str, Any]:
        """Get available asset pairs on the exchange."""


class IExchangeWebsocketService(ABC):
    """Interface for exchange websocket operations."""

    @abstractmethod
    async def start(self) -> None:
        """Start the websocket connection."""

    @abstractmethod
    async def subscribe(self, params: dict[str, Any]) -> None:
        """Subscribe to a specific channel and pair."""

    @abstractmethod
    async def close(self) -> None:
        """Close the websocket connection."""

    @abstractmethod
    async def on_message(
        self, message: dict[str, Any], **kwargs: dict[str, Any]
    ) -> None:
        """Handle incoming messages from the websocket."""


class IStrategy(ABC):
    """Interface for trading strategies"""

    @abstractmethod
    def __init__(
        self,
        state_machine: StateMachine,
        rest_api: IExchangeRESTService,
        config: Configuration,
        orderbook: Orderbook,
        pending_txids: PendingTxids,
        unsold_buy_order_txids: UnsoldBuyOrderTxids,
        event_bus: EventBus,
    ) -> None:
        """Initialize the strategy with necessary services and configurations."""

    @abstractmethod
    def on_ticker_update(self, event: Event) -> None:
        """Handle ticker updates from the exchange."""
        pass

    @abstractmethod
    def on_order_filled(self, event: Event) -> None:
        """Handle order filled events."""
        pass

    @abstractmethod
    def on_order_canceled(self, event: Event) -> None:
        """Handle order canceled events."""
        pass
