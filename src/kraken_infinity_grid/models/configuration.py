# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

# FIXME: add validators

from pydantic import BaseModel, computed_field, field_validator


class BotConfigDTO(BaseModel):
    """
    Data transfer object for the general bot configuration. These values are
    passed via CLI or environment variables.
    """

    # ==========================================================================
    # General attributes
    strategy: str
    exchange: str
    api_public_key: str
    api_secret_key: str
    name: str
    userref: int
    base_currency: str
    quote_currency: str
    fee: float | None = None
    dry_run: bool = False
    max_investment: float

    # We expect these values to be set by the user via CLI or environment
    # variables. Cloup is handling the validation of these values.
    amount_per_grid: float | None
    interval: float | None
    n_open_buy_orders: int | None

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
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

    token: str | None = None
    chat_id: str | None = None

    @computed_field
    def enabled(self) -> bool:
        """Return True if both token and chat_id are truthy values."""
        return bool(self.token and self.chat_id)


class NotificationConfigDTO(BaseModel):
    """Pydantic model for notification service configuration."""

    telegram: TelegramConfigDTO
