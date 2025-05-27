# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#
# Data Transfer objects

from kraken_infinity_grid.models.dto.configuration import (
    BotConfigDTO,
    TelegramConfigDTO,
    DBConfigDTO,
    NotificationConfigDTO,
)

__all__ = ["BotConfigDTO", "TelegramConfigDTO", "DBConfigDTO", "NotificationConfigDTO"]
