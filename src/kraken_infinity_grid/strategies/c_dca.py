# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from logging import getLogger
from typing import Self

from kraken_infinity_grid.strategies.grid_base import GridStrategyBase

LOG = getLogger(__name__)


class CDCAStrategy(GridStrategyBase):

    def _get_order_price(
        self: Self,
        side: str,
        last_price: float,
        extra_sell: bool = False,  # noqa: ARG002
    ) -> float:
        """
        Returns the order price depending on the strategy and side. Also assigns
        a new highest buy price to configuration if there was a new highest buy.
        """
        LOG.debug("Computing the order price...")

        if side == self._exchange_domain.SELL:  # New order is a sell
            # There is no order price for sell orders in cDCA strategy, since no
            # sell orders are placed.
            return None

        if side == self._exchange_domain.BUY:  # New order is a buy
            order_price = last_price * 100 / (100 + 100 * self._config.interval)
            if order_price > self._ticker:
                order_price = self._ticker * 100 / (100 + 100 * self._config.interval)
            return order_price

        raise ValueError(f"Unknown side: {side}!")

    def _check_extra_sell_order(self: Self) -> None:
        """Not applicable for cDCA strategy."""

    def _new_sell_order(
        self: Self,
        order_price: float,  # noqa: ARG002
        txid_to_delete: str | None = None,
    ) -> None:
        """Places a new sell order."""
        if self._config.dry_run:
            LOG.info("Dry run, not placing sell order.")
            return

        LOG.debug("cDCA strategy, not placing sell order.")
        if txid_to_delete is not None:
            self._orderbook_table.remove(filters={"txid": txid_to_delete})
