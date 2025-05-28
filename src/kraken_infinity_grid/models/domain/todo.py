# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from datetime import datetime

from pydantic import BaseModel, Field


class Order(BaseModel):
    """Domain model representing an order in the grid strategy"""

    txid: str
    userref: int
    symbol: str
    side: str
    price: float
    volume: float
    created_at: datetime = Field(default_factory=datetime.now)
