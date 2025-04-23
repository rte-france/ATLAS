"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class OtherNonDispatchable(Equipment):
    """:param maximum_power_forecast: Maximum production capacity forecast
    :type maximum_power_forecast: ForecastingMatrix
    :param da_sell_submitted_volume: Sum of volume of sell offers on the Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    maximum_power_forecast: ForecastingMatrix | None = None
    da_sell_submitted_volume: Timeseries | None = None
