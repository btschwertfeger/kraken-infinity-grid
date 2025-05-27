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


class IExchangeRESTService(ABC):
    """Interface for exchange operations."""

    @abstractmethod
    def check_api_key_permissions(self) -> None:
        """Check if the API key permissions are set correctly."""

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


class IExchangeWebSocketService(ABC):
    """Interface for exchange websocket operations."""

    @abstractmethod
    async def start(self) -> None:
        """Start the websocket connection."""

    @abstractmethod
    async def close(self) -> None:
        """Close the websocket connection."""

    @abstractmethod
    async def subscribe(self, params: dict[str, Any]) -> None:
        """Subscribe to a specific channel and pair."""

    @abstractmethod
    async def on_message(
        self,
        message: dict[str, Any],
        **kwargs: dict[str, Any],
    ) -> None:
        """Handle incoming messages from the websocket."""



