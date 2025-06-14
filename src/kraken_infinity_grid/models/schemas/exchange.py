# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#

"""
FIXME: docstring

All schemas can be extended with additional fields as needed.
"""

from pydantic import BaseModel


class AssetPairInfoSchema(BaseModel):
    """Model for required asset pair information"""

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
    side: str


class PairBalanceSchema(BaseModel):
    base_balance: float
    quote_balance: float
    base_available: float
    quote_available: float


class AssetBalanceSchema(BaseModel):

    asset: str  # Asset name, e.g. "XXBT"
    balance: float  # Current balance of the asset
    hold_trade: float  # Balance held in trades


class CreateOrderResponseSchema(BaseModel):
    """Model for the response of a create order operation"""

    txid: str  # Transaction ID of the created order


class TickerUpdateSchema(BaseModel):
    # This can be extended if needed
    symbol: str
    last: float


class ExecutionsUpdateSchema(BaseModel):
    # This can be extended if needed
    order_id: str
    exec_type: str  # "new", "filled" or "cancelled"


class OnMessageSchema(BaseModel):

    channel: str  # "heartbeat", "status", "ticker", "executions", ...
    type: str  # "update" or "snapshot"
    ticker_data: TickerUpdateSchema | None = None
    executions: list[ExecutionsUpdateSchema] | None = None
