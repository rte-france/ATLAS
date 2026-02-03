"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import Duration, duration
from pydantic import Field, field_validator

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment
from atlas.validators import convert_to_duration


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
    curtailment_cost: Timeseries | LazyTimeseries | None = None
    curtailed_power: Timeseries | LazyTimeseries | None = None
    da_sell_submitted_volume: Timeseries | LazyTimeseries | None = None
    maximum_curtailment_ratio: Timeseries | LazyTimeseries | None = None

    additional_hours: Duration = Field(
        default_factory=lambda: duration(hours=0),
        description="Default optimization period in hours for Solar, Wind, and Load. Overwritten by specific equipment.",
    )

    @field_validator("additional_hours", mode="before")
    @classmethod
    def convert_hours_to_duration(cls, v):
        """Convert various duration formats to Duration objects (hours default)."""
        return convert_to_duration(v)
