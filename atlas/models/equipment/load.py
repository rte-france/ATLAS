"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""


from atlas.enums import LoadType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.equipment import Equipment


class Load(Equipment):
    """
    :param load_type: Load type
    :type load_type: LoadType
    :param maximum_power_forecast: Forecast of the maximum production
    :type maximum_power_forecast: ForecastingMatrix
    :param da_buy_submitted_volume: Sum of volume of purchase offers submitted to the Day Ahead market
    :type da_buy_submitted_volume: Timeseries
    :param power_forecast_high: Year-long demand time series used to formulate the high price forecast scenario
    on Day Ahead
    :type power_forecast_high: Timeseries
    :param power_forecast_low: Year-long demand time series used to formulate the low price forecast scenario
    on Day Ahead
    :type power_forecast_low: Timeseries
    """

    load_type: LoadType | None = None
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_buy_submitted_volume: AbstractTimeseries | None = None
    power_forecast_high: AbstractTimeseries | None = None
    power_forecast_low: AbstractTimeseries | None = None
