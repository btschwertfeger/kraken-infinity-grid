#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2023 Benjamin Thomas Schwertfeger
# GitHub: https://github.com/btschwertfeger
#

"""Module that implements mathematical utility functions"""

from typing import Optional

import numpy as np


def ceil(a: float, precision: Optional[int] = 0) -> float:
    """Round-up to 'precision' comma place"""
    return np.true_divide(np.ceil(a * 10.0**precision), 10.0**precision)  # type: ignore[no-any-return]


def floor(a: float, precision: Optional[int] = 0) -> float:
    """Round-down to 'precision' comma place"""
    return np.true_divide(np.floor(a * 10.0**precision), 10.0**precision)  # type: ignore[no-any-return]
