"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.core.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.equipment import Equipment


class OtherNonDispatchable(Equipment):
    """
    :param maximum_power_forecast: Forecast of the maximum production
    :type maximum_power_forecast: ForecastingMatrix
    :param da_sell_submitted_volume: Sum of volume of sell offers submitted to the Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    """

    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_sell_submitted_volume: AbstractTimeseries | None = None
