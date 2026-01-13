"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from pydantic import Field, field_serializer, field_validator

from atlas.enum import InflowFrequency
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment
from atlas.validators import parse_list_float, serializer_list_float


class Hydro(Equipment):
    """
    :param fragment_prices: List of spreads applied to hydro equipment water values, to assign prices to fragments
    calculated with fragment_volumes
    :type fragment_prices: list[float]
    :param fragment_volumes: List of percentages used to divide the interval between MaximumPower and MinimumPower
    into different fragments
    :type fragment_volumes: list[float]
    :param stored_energy: Storage capacity of energy for different time horizons
    :type stored_energy: ForecastingMatrix
    :param da_sell_submitted_volume:Sum of volume of sell offers submitted to the Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    :param energy_target: Daily storage target. Used for countries where inflows are not provided in input data
    :type energy_target: Timeseries
    :param inflows: Hydro daily inflows (in energy)
    :type inflows: Timeseries
    :param initial_level: Energy contained in the hydro reservoir prior to execution of any ATLAS module
    :type initial_level: Timeseries
    :param maximum_energy: Maximum energy storage capacity
    :type maximum_energy: Timeseries | LazyTimeseries
    :param minimum_energy: Minimum energy storage capacity
    :type minimum_energy: Timeseries | LazyTimeseries
    :param maximum_power: Maximum power
    :type maximum_power: Timeseries | LazyTimeseries
    :param minimum_power: Minimum power
    :type minimum_power: Timeseries | LazyTimeseries
    :param inflow_frequency: Frequency of inflow data. Possible values: 'Monthly', 'Daily'
    :type inflow_frequency: InflowFrequency
    :param energy_target_frequency: Frequency of energy target data. Possible values: 'Monthly', 'Daily'
    :type energy_target_frequency: InflowFrequency
    """

    fragment_prices: list[float] | None = Field(
        None,
        description="List of positive prices",
    )
    fragment_volumes: list[float] | None = Field(None, description="List of positive volumes")

    stored_energy: ForecastingMatrix | LazyForecastingMatrix | None = None

    da_sell_submitted_volume: Timeseries | LazyTimeseries | None = None
    energy_target: Timeseries | LazyTimeseries | None = None
    inflow_frequency: InflowFrequency | None = Field(None, description="Possible values: 'Monthly', 'Daily'")
    energy_target_frequency: InflowFrequency | None = Field(
        None,
        description="Possible values: 'Monthly', 'Daily'",
    )
    inflows: Timeseries | LazyTimeseries | None = None
    initial_level: Timeseries | LazyTimeseries | None = None
    maximum_energy: Timeseries | LazyTimeseries | None = None
    minimum_energy: Timeseries | LazyTimeseries | None = None
    maximum_power: Timeseries | LazyTimeseries | None = None
    minimum_power: Timeseries | LazyTimeseries | None = None

    @field_validator("fragment_prices", "fragment_volumes", mode="before")
    @classmethod
    def validate_fragment_prices_and_volumes(cls, value: Any):
        return parse_list_float(value)

    @field_serializer("fragment_prices", "fragment_volumes", mode="plain")
    def serialize_fragment_prices_and_volumes(self, value: list[float] | None) -> str | None:
        """Serialize fragment prices and volumes to a string."""
        return serializer_list_float(value)
