"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.equipment import Equipment


class Solar(Equipment):
    """
    :param installed_capacity: Installed capacity
    :type installed_capacity: float
    :param maximum_power_forecast: Forecast of the maximum production
    :type maximum_power_forecast:
    :param curtailment_cost: Equipment curtailment cost. Positive by convention
    :type curtailment_cost: Timeseries
    :param curtailed_power: Total curtailed power following each Portfolio Optimization
    :type curtailed_power: Timeseries
    :param da_sell_submitted_volume: Sum of volume of sell offers submitted to the Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    :param maximum_curtailment_ratio: Ratio of maximum production power (indicated by MaximumPowerForecast) that can be
    curtailed
    :type maximum_curtailment_ratio: Timeseries
    """

    installed_capacity: float | None = Field(
        None,
        ge=0,
        description="Installed capacity (must be positive)",
    )
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix | None = None
    curtailment_cost: AbstractTimeseries | None = None
    curtailed_power: AbstractTimeseries | None = None
    da_sell_submitted_volume: AbstractTimeseries | None = None
    maximum_curtailment_ratio: AbstractTimeseries | None = None
