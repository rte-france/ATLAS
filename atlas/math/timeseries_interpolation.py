"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from enum import Enum


class TimeSeriesInterpolation(Enum):
    """
    Defines interpolation types for TimeSeries objects
    """

    CONSTANT = 0
    LINEAR = 1
    LINEAR_AVERAGE = 2


CONSTANT = TimeSeriesInterpolation.CONSTANT
LINEAR = TimeSeriesInterpolation.LINEAR
LINEAR_AVERAGE = TimeSeriesInterpolation.LINEAR_AVERAGE
