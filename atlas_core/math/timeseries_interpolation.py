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
