# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from abc import ABC, abstractmethod
from typing import Any, Self

from kraken_infinity_grid.core.event_bus import Event, EventBus
from kraken_infinity_grid.core.state_machine import StateMachine
from kraken_infinity_grid.infrastructure.database import DBConnect
from kraken_infinity_grid.models.dto import BotConfigDTO


class IStrategy(ABC):
    """Interface for trading strategies"""

    @abstractmethod
    def __init__(
        self: Self,
        config: BotConfigDTO,
        event_bus: EventBus,
        state_machine: StateMachine,
        db: DBConnect,
    ) -> None:
        """Initialize the strategy with necessary services and configurations."""

    @abstractmethod
    async def run(self) -> None:
        """Start the strategy."""

    @abstractmethod
    def on_ticker_update(self: Self, event: Event) -> None:
        """Handle ticker updates from the exchange."""

    @abstractmethod
    def on_order_filled(self: Self, event: Event) -> None:
        """Handle order filled events."""

    @abstractmethod
    def on_order_canceled(self: Self, event: Event) -> None:
        """Handle order canceled events."""

    @abstractmethod
    def on_prepare_for_trading(self: Self, event: Event) -> None:
        """Prepare the strategy for trading."""

    def _get_exchange_adapter(self: Self, exchange: str, adapter_type: str) -> Any:
        """Get the exchange adapter for the specified exchange and adapter type."""
        if exchange == "Kraken":
            from kraken_infinity_grid.adapters.exchanges.kraken import (  # pylint: disable=import-outside-toplevel
                KrakenExchangeRESTServiceAdapter,
                KrakenExchangeWebsocketServiceAdapter,
            )

            if adapter_type == "rest":
                return KrakenExchangeRESTServiceAdapter
            if adapter_type == "websocket":
                return KrakenExchangeWebsocketServiceAdapter
        raise ValueError(
            f"Unsupported exchange or adapter type: {exchange}, {adapter_type}",
        )
