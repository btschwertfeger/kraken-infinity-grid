# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from decimal import Decimal
from logging import getLogger
from time import sleep
from typing import TYPE_CHECKING, Self

from kraken_infinity_grid.core.event_bus import Event
from kraken_infinity_grid.strategies.grid_base import GridStrategyBase

if TYPE_CHECKING:
    from kraken_infinity_grid.models.schemas.exchange import OrderInfoSchema
LOG = getLogger(__name__)


class SwingStrategy(GridStrategyBase):

    def _get_order_price(
        self: Self,
        side: str,
        last_price: float,
        extra_sell: bool = False,
    ) -> float:
        """
        Returns the order price depending on the strategy and side. Also assigns
        a new highest buy price to configuration if there was a new highest buy.
        """
        LOG.debug("Computing the order price...")
        order_price: float
        price_of_highest_buy = self._configuration_table.get()["price_of_highest_buy"]
        last_price = float(last_price)

        if side == self._exchange_domain.SELL:  # New order is a sell
            if extra_sell:
                # Extra sell order when SWING
                # 2x interval above [last close price | price of highest buy]
                order_price = (
                    last_price
                    * (1 + self._config.interval)
                    * (1 + self._config.interval)
                )
                if order_price < price_of_highest_buy:
                    order_price = (
                        price_of_highest_buy
                        * (1 + self._config.interval)
                        * (1 + self._config.interval)
                    )

            else:
                # Regular sell order (even for SWING) (cDCA will trigger this
                # but it will be filtered out later)
                if last_price > price_of_highest_buy:
                    self._configuration_table.update(
                        {"price_of_highest_buy": last_price},
                    )

                # Sell price 1x interval above buy price
                order_price = last_price * (1 + self._config.interval)
                if self._ticker > order_price:
                    order_price = self._ticker * (1 + self._config.interval)
            return order_price

        if side == self._exchange_domain.BUY:  # New order is a buy
            order_price = last_price * 100 / (100 + 100 * self._config.interval)
            if order_price > self._ticker:
                order_price = self._ticker * 100 / (100 + 100 * self._config.interval)
            return order_price

        raise ValueError(f"Unknown side: {side}!")

    def _check_extra_sell_order(self: Self) -> None:
        """
        Checks if an extra sell order can be placed. This only applies for the
        SWING strategy.
        """
        LOG.debug("Checking if extra sell order can be placed...")
        if (
            self._orderbook_table.count(filters={"side": self._exchange_domain.SELL})
            == 0
        ):
            fetched_balances = self._rest_api.get_pair_balance(
                self._config.base_currency,
                self._config.quote_currency,
            )

            if (
                fetched_balances.base_available * self._ticker
                > self._runtime_attrs.amount_per_grid_plus_fee
            ):
                order_price = self._get_order_price(
                    side=self._exchange_domain.SELL,
                    last_price=self._ticker,
                    extra_sell=True,
                )
                self._event_bus.publish(
                    Event(
                        type="notification",
                        data={
                            "message": f"ℹ️ {self._config.name}: Placing extra sell order",  # noqa: RUF001
                        },
                    ),
                )
                self._handle_arbitrage(
                    side=self._exchange_domain.SELL,
                    order_price=order_price,
                )

    def _new_sell_order(
        self: Self,
        order_price: float,
        txid_to_delete: str | None = None,
    ) -> None:
        """Places a new sell order."""
        if self._config.dry_run:
            LOG.info("Dry run, not placing sell order.")
            return

        LOG.debug("Check conditions for placing a sell order...")

        # ======================================================================
        volume: float | None = None
        if txid_to_delete is not None:  # If corresponding buy order filled
            # GridSell always has txid_to_delete set.

            # Add the txid of the corresponding buy order to the unsold buy
            # order txids in order to ensure that the corresponding sell order
            # will be placed - even if placing now fails.
            if not self._unsold_buy_order_txids_table.get(
                filters={"txid": txid_to_delete},
            ).first():
                self._unsold_buy_order_txids_table.add(
                    txid=txid_to_delete,
                    price=order_price,
                )

            # ==================================================================
            # Get the corresponding buy order in order to retrieve the volume.
            corresponding_buy_order: OrderInfoSchema = (
                self._rest_api.get_order_with_retry(
                    txid=txid_to_delete,
                )
            )

            # In some cases the corresponding buy order is not closed yet and
            # the vol_exec is missing. In this case, the function will be
            # called again after a short delay.
            if (
                corresponding_buy_order.status != self._exchange_domain.CLOSED
                or corresponding_buy_order.vol_exec == 0
            ):
                LOG.warning(
                    "Can't place sell order, since the corresponding buy order"
                    " is not closed yet. Retry in 1 second. (order: %s)",
                    corresponding_buy_order,
                )
                sleep(1)
                self._new_sell_order(
                    order_price=order_price,
                    txid_to_delete=txid_to_delete,
                )
                return

        order_price = float(
            self._rest_api.truncate(
                amount=order_price,
                amount_type="price",
                base_currency=self._config.base_currency,
                quote_currency=self._config.quote_currency,
            ),
        )

        # Respect the fee to not reduce the quote currency over time, while
        # accumulating the base currency.
        volume = float(
            self._rest_api.truncate(
                amount=Decimal(self._config.amount_per_grid)
                / (Decimal(order_price) * (1 - (2 * Decimal(self._config.fee)))),
                amount_type="volume",
                base_currency=self._config.base_currency,
                quote_currency=self._config.quote_currency,
            ),
        )

        # ======================================================================
        # Check if there is enough base currency available for selling.
        fetched_balances = self._rest_api.get_pair_balance(
            self._config.base_currency,
            self._config.quote_currency,
        )
        if fetched_balances.base_available >= volume:
            # Place new sell order, append id to pending list, and delete
            # corresponding buy order from local orderbook.
            LOG.info(
                "Placing order to sell %s %s @ %s %s.",
                volume,
                self._config.base_currency,
                order_price,
                self._config.quote_currency,
            )

            placed_order = self._rest_api.create_order(
                ordertype="limit",
                side=self._exchange_domain.SELL,
                volume=volume,
                base_currency=self._config.base_currency,
                quote_currency=self._config.quote_currency,
                price=order_price,
                userref=self._config.userref,
                validate=self._config.dry_run,
            )

            self._pending_txids_table.add(placed_order.txid)

            if txid_to_delete is not None:
                # Other than with buy orders, we can only delete the
                # corresponding buy order if the sell order was placed.
                self._orderbook_table.remove(filters={"txid": txid_to_delete})
                self._unsold_buy_order_txids_table.remove(txid=txid_to_delete)

            self._assign_order_by_txid(txid=placed_order.txid)
            return

        # ======================================================================
        # Not enough funds to sell
        message = f"⚠️ {self._symbol}"
        message += f"├ Not enough {self._config.base_currency}"
        message += f"├ to sell {volume} {self._config.base_currency}"
        message += f"└ for {order_price} {self._config.quote_currency}"
        self._event_bus.publish(
            Event(type="notification", data={"message": message}),
        )
        LOG.warning("Current balances: %s", fetched_balances)

        if txid_to_delete is not None:
            # TODO: Check if this is appropriate or not
            #       Added logging statement to monitor occurrences
            # ... This would only be the case for GridHODL and SWING, while
            # those should always have enough base currency available... but
            # lets check this for a while.
            LOG.warning(
                "TODO: Not enough funds to place sell order for txid %s",
                txid_to_delete,
            )
            self._orderbook_table.remove(filters={"txid": txid_to_delete})
