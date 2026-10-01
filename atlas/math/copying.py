"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

This module provides the deep copy shared by every timeseries and matrix.
"""

from __future__ import annotations

import copy
from collections.abc import Container
from typing import Any

import polars as pl


def deepcopy_sharing_frames[T](obj: T, memo: dict[int, Any], skip: Container[str] = ()) -> T:
    """Deep copy a math object, sharing its polars frames with the original.

    Polars frames are never mutated in place: an ``inplace=True`` operation rebinds the object to a
    new frame. Sharing them is therefore safe, while every other attribute is deep copied.

    :param obj: Timeseries or matrix to copy
    :type obj: T
    :param memo: Memo dictionary of the ongoing :func:`copy.deepcopy`
    :type memo: dict[int, Any]
    :param skip: Attributes left out of the copy, typically caches the caller resets afterwards
    :type skip: Container[str]
    :return: An independent object holding the same frames
    :rtype: T

    Example:

        >>> class Timeseries:
        ...     def __deepcopy__(self, memo):
        ...         return deepcopy_sharing_frames(self, memo)
        >>> copied = copy.deepcopy(timeseries)
        >>> copied.timeseries is timeseries.timeseries
        True
    """
    copied = object.__new__(type(obj))
    memo[id(obj)] = copied
    for name, value in vars(obj).items():
        if name in skip:
            continue
        shared = isinstance(value, (pl.DataFrame, pl.LazyFrame))
        setattr(copied, name, value if shared else copy.deepcopy(value, memo))
    return copied
