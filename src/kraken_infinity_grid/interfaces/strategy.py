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
    DBConnect
)
from kraken_infinity_grid.interfaces.exchange import IExchangeRESTService
from kraken_infinity_grid.models.dto import BotConfigDTO

class IStrategy(ABC):
    """Interface for trading strategies"""

    @abstractmethod
    def __init__(
        self,
        config: BotConfigDTO,
        rest_api: IExchangeRESTService,
        event_bus: EventBus,
        state_machine: StateMachine,
        db: DBConnect,
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
