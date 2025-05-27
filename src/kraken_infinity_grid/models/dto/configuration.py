# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

# FIXME: add validators

from pydantic import BaseModel, field_validator, Field


class BotConfigDTO(BaseModel):
    """Data transfer object for bot configuration"""

    api_key: str
    secret_key: str
    userref: int
    strategy: str
    name: str
    interval: float
    amount_per_grid: float
    max_investment: float
    n_open_buy_orders: int
    base_currency: str
    quote_currency: str
    fee: float | None = None
    dry_run: bool = False

    @field_validator("strategy")
    def validate_strategy(self, value):
        """Validate the strategy value."""
        if value not in (valid_strategies := ("GridHODL", "GridSell", "SWING", "cDCA")):
            raise ValueError(f"Strategy must be one of: {', '.join(valid_strategies)}")
        return value


class DBConfigDTO(BaseModel):
    sqlite_file: str | None = None
    db_user: str | None = None
    db_password: str | None = None
    db_host: str | None = None
    db_port: str | None = None
    db_name: str = "kraken_infinity_grid"


class TelegramConfigDTO(BaseModel):
    """Pydantic model for Telegram notification configuration."""

    enabled: bool = Field(default=False)
    bot_token: str = Field(...)  # required field
    chat_id: str = Field(...)  # required field


class NotificationConfigDTO(BaseModel):
    """Pydantic model for notification service configuration."""

    telegram: TelegramConfigDTO | None = None
