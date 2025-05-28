# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

from pydantic import BaseModel

"""
FIXME: docstring

All schemas can be extended with additional fields as needed.
"""

class AssetPairInfoSchema(BaseModel):
    """Model for required asset pair information"""

    altname: str  # e.g. "XBTUSD"
    base: str  # "XXBT"
    quote: str  # "ZUSD"
    cost_decimals: int  # Number of decimals for cost, e.g. 5
    # Fees for maker orders, e.g. [[0, 0.25], [10000, 0.2], ...]
    fees_maker: list[list[float]]


class OrderInfoSchema(BaseModel):
    """Model for order information"""

    status: str  # e.g. "open", "closed", "canceled"
    vol_exec: float  # Volume executed
    pair: str  # altname / Asset Pair Name
    userref: int  # User reference number
    txid: str  # transaction ID
    price: float  # primary price
    type: str  # Side (buy or sell) # FIXME: rename to side?


class AssetBalanceSchema(BaseModel):

    asset: str  # Asset name, e.g. "XXBT"
    balance: float # Current balance of the asset
    hold_trade: float  # Balance held in trades

class CreateOrderResponseSchema(BaseModel):
    """Model for the response of a create order operation"""

    txid: str  # Transaction ID of the created order
