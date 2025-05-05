"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.enum import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Load(Equipment):
    """:param load_type: Load type
    :type load_type: LoadType
    :param maximum_power_forecast: Maximum production capacity forecast
    :type maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    :param da_buy_submitted_volume: Sum of volume of buy offers on the Day Ahead market
    :type da_buy_submitted_volume: Timeseries | LazyTimeseries
    :param power_forecast_high: Annual high consumption record used to formulate the high price forecast scenario on
    Day Ahead
    :type power_forecast_high: Timeseries | LazyTimeseries
    :param power_forecast_low: Annual high consumption record used to formulate the low price forecast scenario on
    Day Ahead
    :type power_forecast_low: Timeseries | LazyTimeseries
    """

    load_type: LoadType | None = None
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_buy_submitted_volume: Timeseries | LazyTimeseries | None = None
    power_forecast_high: Timeseries | LazyTimeseries | None = None
    power_forecast_low: Timeseries | LazyTimeseries | None = None
