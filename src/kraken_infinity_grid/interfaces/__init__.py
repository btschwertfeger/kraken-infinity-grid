# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from kraken_infinity_grid.interfaces.interfaces import (
    IExchangeRESTService,
    IExchangeWebSocketService,
    IStrategy,
)

__all__ = [
    "IExchangeRESTService",
    "IExchangeWebSocketService",
    "IStrategy",
]
