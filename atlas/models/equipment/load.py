"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.config import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Load(Equipment):
    """:param load_type: Load type
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
    maximum_power_forecast: ForecastingMatrix | None = None
    da_buy_submitted_volume: Timeseries | None = None
    power_forecast_high: Timeseries | None = None
    power_forecast_low: Timeseries | None = None
