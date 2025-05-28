# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from logging import getLogger

from kraken_infinity_grid.core.event_bus import Event
from kraken_infinity_grid.interfaces import INotificationChannel
from kraken_infinity_grid.models.dto.configuration import NotificationConfigDTO

LOG = getLogger(__name__)


class NotificationService:
    """Service for sending notifications through configured channels."""

    def __init__(self, config: NotificationConfigDTO):
        self.__channels: list[INotificationChannel] = []
        self.__config = config
        self._setup_channels_from_config()

    def _setup_channels_from_config(self):
        """Set up notification channels from the loaded config."""
        if self.__config.telegram and self.__config.telegram.enabled:
            self.add_telegram_channel(
                bot_token=self.__config.telegram.bot_token,
                chat_id=self.__config.telegram.chat_id,
            )

    def add_channel(self, channel: INotificationChannel):
        """Add a notification channel to the service."""
        self.__channels.append(channel)

    def add_telegram_channel(self, bot_token: str, chat_id: str):
        """Convenience method to add a Telegram notification channel."""
        from kraken_infinity_grid.adapters.notification import (
            TelegramNotificationChannelAdapter,
        )

        self.add_channel(TelegramNotificationChannelAdapter(bot_token, chat_id))

    def notify(self, message: str) -> bool:
        """Send a notification through all configured channels.

        Args:
            message: The message to send

        Returns:
            bool: True if the message was sent through at least one channel
        """
        LOG.info("Sending notification: %s", message)
        if not self.__channels:
            return False

        success = False
        for channel in self.__channels:
            if channel.send(message):
                success = True

        return success

    def on_notification(self, event: Event) -> None:
        """Handle a notification event."""
        self.notify(event.data["message"])
