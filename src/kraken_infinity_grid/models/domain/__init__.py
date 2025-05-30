# -*- mode: python; coding: utf-8 -*-
#
# Copyright (C) 2025 Benjamin Thomas Schwertfeger
# All rights reserved.
# https://github.com/btschwertfeger
#
# Domain models

from pydantic import BaseModel


class ExchangeDomain(BaseModel):

    # General
    EXCHANGE: str

    # Order sides
    BUY: str
    SELL: str

    # Order states
    OPEN: str
    CLOSED: str
    CANCELED: str
    EXPIRED: str
    PENDING: str
