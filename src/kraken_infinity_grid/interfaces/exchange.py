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
from typing import Any, Self

from kraken_infinity_grid.models.domain import ExchangeDomain
from kraken_infinity_grid.models.schemas.exchange import (
    AssetBalanceSchema,
    AssetPairInfoSchema,
    CreateOrderResponseSchema,
    OrderInfoSchema,
    PairBalanceSchema,
)


class IExchangeRESTService(ABC):
    """Interface for exchange operations."""

    @abstractmethod
    def check_api_key_permissions(self) -> None:
        """Check if the API key permissions are set correctly."""

    @abstractmethod
    def check_exchange_status(self, tries: int = 0) -> None:
        """Check if the exchange is online and operational.

        Raises an exception if the exchange is not online.
        """

    # == Getters for exchange user operations ==================================
    @abstractmethod
    def get_orders_info(self, txid: str | None) -> OrderInfoSchema | None:
        """Get information about the user on the exchange."""

    @abstractmethod
    def get_open_orders(
        self,
        userref: int,
        trades: bool = None,
    ) -> list[OrderInfoSchema]:
        """Get all open orders for a userref."""

    @abstractmethod
    def get_order_with_retry(
        self: Self,
        txid: str,
        tries: int = 0,
        max_tries: int = 5,
        exit_on_fail: bool = True,
    ) -> dict | None:
        """Get order information with retry logic.

        If exit_on_fail is True, the program will exit if the order cannot be retrieved.
        """

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

    @abstractmethod
    def get_pair_balance(
        self: Self,
        base_currency: str,
        quote_currency: str,
    ) -> PairBalanceSchema:
        """Get the balance for a specific currency pair."""

    @abstractmethod
    @classmethod
    def altname(base_currency: str, quote_currency: str) -> str:
        """Returns the alternative name for the given base and quote currency."""

    @abstractmethod
    @classmethod
    def symbol(base_currency: str, quote_currency: str) -> str:
        """Returns the symbol for the given base and quote currency."""

    # == Getters for exchange trade operations =================================
    @abstractmethod
    def create_order(
        self,
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

    @abstractmethod
    def cancel_order(self, txid: str) -> None:
        """Cancel an order."""

    @abstractmethod
    def truncate(
        self,
        amount: float,
        amount_type: str,
        base_currency: str,
        quote_currency: str,
    ) -> str:
        """Truncate amount according to exchange precision."""

    # == Getters for exchange market operations ================================
    @abstractmethod
    def get_system_status(self) -> str:
        """
        Get the current system status of the exchange.

        Must be "online" to succeed.
        """

    @abstractmethod
    def get_asset_pair_info(
        self,
        base_currency: str,
        quote_currency: str,
    ) -> AssetPairInfoSchema:
        """Get available asset pair info from the exchange."""

    @abstractmethod
    def get_exchange_domain(self) -> ExchangeDomain:
        """Get the current order side (buy/sell) for the strategy."""


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
