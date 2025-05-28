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

from kraken_infinity_grid.models.schemas.exchange import (
    AssetPairInfoSchema,
    OrderInfoSchema,
    AssetBalanceSchema,CreateOrderResponseSchema
)


class IExchangeRESTService(ABC):
    """Interface for exchange operations."""

    @abstractmethod
    def check_api_key_permissions(self) -> None:
        """Check if the API key permissions are set correctly."""

    # == Getters for exchange user operations ==================================
    @abstractmethod
    def get_orders_info(self, txid: str | None) -> OrderInfoSchema | None:
        """Get information about the user on the exchange."""

    @abstractmethod
    def get_open_orders(self, userref: int, trades: bool = None) -> OrderInfoListSchema:
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
    def get_balances(self) -> list[AssetBalanceSchema]:
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
    ) -> CreateOrderResponseSchema:
        """Create a new order."""

    @abstractmethod
    def cancel_order(self, txid: str) ->None:
        """Cancel an order."""

    @abstractmethod
    def truncate(self, amount: float, amount_type: str, pair: str) -> str:
        """Truncate amount according to exchange precision."""

    # == Getters for exchange market operations ================================
    @abstractmethod
    def get_system_status(self) -> str:
        """
        Get the current system status of the exchange.

        Must be "online" to succeed.
        """

    @abstractmethod
    def get_asset_pair_info(self, pair: str) -> AssetPairInfoSchema:
        """Get available asset pair info from the exchange."""


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
