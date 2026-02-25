"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import Duration
from pydantic import Field, field_validator

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.equipment import Equipment
from atlas.validators import convert_to_duration


class OtherNonDispatchable(Equipment):
    """
    :param maximum_power_forecast: Forecast of the maximum production
    :type maximum_power_forecast: ForecastingMatrix
    :param da_sell_submitted_volume: Sum of volume of sell offers submitted to the Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    """

    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_sell_submitted_volume: AbstractTimeseries | None = None

    additional_hours: Duration | None = Field(
        None,
        description="Default optimization period for other non dispatchable equipment.",
    )

    @field_validator("additional_hours", mode="before")
    @classmethod
    def parse_duration(cls, v):
        """Convert various duration formats to Duration objects (hours default)."""
        return convert_to_duration(v)
