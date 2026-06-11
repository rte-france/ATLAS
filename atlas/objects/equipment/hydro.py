"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from pydantic import BaseModel, Field, field_serializer, field_validator

from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.core.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.enums import InflowFrequency
from atlas.objects.equipment.equipment import Equipment
from atlas.validators import parse_list_float, serializer_list_float


class FragmentData(BaseModel):
    """Data structure to hold fragment volume and price information."""

    volume: float
    price: float


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
    :type maximum_energy: AbstractTimeseries
    :param minimum_energy: Minimum energy storage capacity
    :type minimum_energy: AbstractTimeseries
    :param maximum_power: Maximum power
    :type maximum_power: AbstractTimeseries
    :param minimum_power: Minimum power
    :type minimum_power: AbstractTimeseries
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

    da_sell_submitted_volume: AbstractTimeseries | None = None
    energy_target: AbstractTimeseries | None = None
    inflow_frequency: InflowFrequency | None = Field(None, description="Possible values: 'Monthly', 'Daily'")
    energy_target_frequency: InflowFrequency | None = Field(
        None,
        description="Possible values: 'Monthly', 'Daily'",
    )
    inflows: AbstractTimeseries | None = None
    initial_level: AbstractTimeseries | None = None
    maximum_energy: AbstractTimeseries | None = None
    minimum_energy: AbstractTimeseries | None = None
    maximum_power: AbstractTimeseries | None = None
    minimum_power: AbstractTimeseries | None = None

    @field_validator("fragment_prices", "fragment_volumes", mode="before")
    @classmethod
    def validate_fragment_prices_and_volumes(cls, value: Any):
        return parse_list_float(value)

    @field_serializer("fragment_prices", "fragment_volumes", mode="plain")
    def serialize_fragment_prices_and_volumes(self, value: list[float] | None) -> str | None:
        """Serialize fragment prices and volumes to a string."""
        return serializer_list_float(value)

    @property
    def fragment_data(self) -> dict[int, FragmentData]:
        if not self.fragment_prices or not self.fragment_volumes:
            return {}

        if len(self.fragment_volumes) != len(self.fragment_prices):
            raise ValueError("Fragment volumes and prices must have the same length")

        return {
            i: FragmentData(volume=v, price=p)
            for i, (v, p) in enumerate(zip(self.fragment_volumes, self.fragment_prices, strict=True))
        }
