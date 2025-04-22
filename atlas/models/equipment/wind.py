"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import ConfigDict, Field

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Wind(Equipment):
    """:param installed_capacity: Installed capacity
    :type installed_capacity: float
    :param maximum_power_forecast: Sum of volume of sell offers on the Day Ahead market
    :type maximum_power_forecast: ForecastingMatrix
    :param curtailed_power: Stores capping at the end of each Portfolio Optimization
    :type curtailed_power: ForecastingMatrix
    :param curtailment_cost: Equipment capping cost
    :type curtailment_cost: Timeseries
    :param da_sell_submitted_volume: Sum of volume of sell offers on the Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    :param maximum_curtailment_ratio: Sum of volume of sell offers on the Day Ahead market
    :type maximum_curtailment_ratio: Timeseries
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    installed_capacity: float | None = Field(
        None,
        gt=0,
        description="Installed capacity (must be positive)",
    )
    maximum_power_forecast: ForecastingMatrix | None = None
    curtailed_power: ForecastingMatrix | None = None
    curtailment_cost: Timeseries | None = None
    da_sell_submitted_volume: Timeseries | None = None
    maximum_curtailment_ratio: Timeseries | None = None
