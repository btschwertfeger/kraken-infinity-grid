# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from logging import getLogger

import requests

from kraken_infinity_grid.interfaces import INotificationChannel
from typing import Self

LOG = getLogger(__name__)


class TelegramNotificationChannelAdapter(INotificationChannel):
    """Telegram implementation of the notification channel."""

    def __init__(self: Self, bot_token: str, chat_id: str) -> None:
        self.__chat_id = chat_id
        self.__base_url = f"https://api.telegram.org/bot{bot_token}"

    def send(self: Self, message: str) -> bool:
        """Send a notification message through Telegram."""
        LOG.debug(f"Sending Telegram notification: {message}")
        try:
            url = f"{self.__base_url}/sendMessage"
            response = requests.post(
                url,
                data={
                    "chat_id": self.__chat_id,
                    "text": message,
                    "parse_mode": "markdown",
                },
                timeout=10,
            )
            return response.status_code == 200
        except Exception as e:
            LOG.error(f"Failed to send Telegram notification: {e}")
            return False
