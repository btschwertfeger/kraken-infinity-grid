# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from kraken_infinity_grid.models.dto.configuration import NotificationConfigDTO

from kraken_infinity_grid.interfaces import INotificationChannel




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
        if not self.__channels:
            return False

        success = False
        for channel in self.__channels:
            if channel.send(message):
                success = True

        return success

    def build_update_message() -> str:
        """Build a message for updates."""
        balances = self.__s.get_balances()

        message = f"👑 {self.__s.symbol}\n"
        message += f"└ Price » {self.__s.ticker.last} {self.__s.quote_currency}\n\n"

        message += "⚜️ Account\n"
        message += f"├ Total {self.__s.base_currency} » {balances['base_balance']}\n"
        message += f"├ Total {self.__s.quote_currency} » {balances['quote_balance']}\n"
        message += (
            f"├ Available {self.__s.quote_currency} » {balances['quote_available']}\n"
        )
        message += f"├ Available {self.__s.base_currency} » {balances['base_available'] - float(self.__s.configuration.get()['vol_of_unfilled_remaining'])}\n"  # noqa: E501
        message += f"├ Unfilled surplus of {self.__s.base_currency} » {self.__s.configuration.get()['vol_of_unfilled_remaining']}\n"  # noqa: E501
        message += f"├ Wealth » {round(balances['base_balance'] * self.__s.ticker.last + balances['quote_balance'], self.__s.cost_decimals)} {self.__s.quote_currency}\n"  # noqa: E501
        message += f"└ Investment » {round(self.__s.investment, self.__s.cost_decimals)} / {self.__s.max_investment} {self.__s.quote_currency}\n\n"  # noqa: E501

        message += "💠 Orders\n"
        message += f"├ Amount per Grid » {self.__s.amount_per_grid} {self.__s.quote_currency}\n"
        message += f"└ Open orders » {self.__s.orderbook.count()}\n"

        message += "\n```\n"
        message += f" 🏷️ Price in {self.__s.quote_currency}\n"
        max_orders_to_list: int = 5

        next_sells = [
            order["price"]
            for order in self.__s.orderbook.get_orders(
                filters={"side": "sell"},
                order_by=("price", "ASC"),
                limit=max_orders_to_list,
            )
        ]
        next_sells.reverse()

        if (n_sells := len(next_sells)) == 0:
            message += f"└───┬> {self.__s.ticker.last}\n"
        else:
            for index, sell_price in enumerate(next_sells):
                change = (sell_price / self.__s.ticker.last - 1) * 100
                if index == 0:
                    message += f" │  ┌[ {sell_price} (+{change:.2f}%)\n"
                elif index <= n_sells - 1 and index != max_orders_to_list:
                    message += f" │  ├[ {sell_price} (+{change:.2f}%)\n"
            message += f" └──┼> {self.__s.ticker.last}\n"

        next_buys = [
            order["price"]
            for order in self.__s.orderbook.get_orders(
                filters={"side": "buy"},
                order_by=("price", "DESC"),
                limit=max_orders_to_list,
            )
        ]
        if (n_buys := len(next_buys)) != 0:
            for index, buy_price in enumerate(next_buys):
                change = (buy_price / self.__s.ticker.last - 1) * 100
                if index < n_buys - 1 and index != max_orders_to_list:
                    message += f"    ├[ {buy_price} ({change:.2f}%)\n"
                else:
                    message += f"    └[ {buy_price} ({change:.2f}%)"
        message += "\n```"

        self.send_to_telegram(message)
        self.__s.configuration.update({"last_telegram_update": datetime.now()})

