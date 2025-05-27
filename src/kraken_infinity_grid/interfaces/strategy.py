# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from abc import ABC, abstractmethod

from kraken_infinity_grid.core.event_bus import Event, EventBus
from kraken_infinity_grid.core.state_machine import StateMachine
from kraken_infinity_grid.infrastructure.database import (
    Configuration,
    Orderbook,
    PendingTXIDs,
    UnsoldBuyOrderTXIDs,
)
from kraken_infinity_grid.interfaces.exchange import IExchangeRESTService

class IStrategy(ABC):
    """Interface for trading strategies"""

    @abstractmethod
    def __init__(
        self,
        state_machine: StateMachine,
        rest_api: IExchangeRESTService,
        config: Configuration,
        orderbook: Orderbook,
        pending_txids: PendingTXIDs,
        unsold_buy_order_txids: UnsoldBuyOrderTXIDs,
        event_bus: EventBus,
    ) -> None:
        """Initialize the strategy with necessary services and configurations."""

    @abstractmethod
    def on_ticker_update(self, event: Event) -> None:
        """Handle ticker updates from the exchange."""

    @abstractmethod
    def on_order_filled(self, event: Event) -> None:
        """Handle order filled events."""

    @abstractmethod
    def on_order_canceled(self, event: Event) -> None:
        """Handle order canceled events."""

    @abstractmethod
    def on_prepare_for_trading(self, event: Event) -> None:
        """Prepare the strategy for trading."""
