"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math

from pydantic import BaseModel, Field

from atlas.enums import InflowFrequency
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.equipment import Equipment
from atlas.validators import PipeSeparatedFloats


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

    fragment_prices: PipeSeparatedFloats = Field(
        None,
        description="List of positive prices",
    )
    fragment_volumes: PipeSeparatedFloats = Field(None, description="List of positive volumes")

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

    def bid_volumes(self, capacity: float, minimal_fragment_size: float) -> dict[int, float]:
        """
        Split *capacity* across the unit's fragments, dropping the ones too small to bid.

        Each fragment takes its share of *capacity*; fragments landing below
        *minimal_fragment_size* are dropped and their volume is redistributed over the
        remaining ones, so the unit still offers its full capacity. When every fragment is
        too small, the whole capacity is bid as the middle fragment instead.

        Shared by the day-ahead and intraday order modules, which bid the same fragments.

        :param capacity: Power available at the timestamp being priced
        :type capacity: float
        :param minimal_fragment_size: Smallest volume worth submitting as an order
        :type minimal_fragment_size: float
        :return: Volume per fragment category, keyed as in :attr:`fragment_data`
        :rtype: dict[int, float]

        :example:

        With ``fragment_volumes = [0.05, 0.25, 0.7]`` and a capacity of 100 MW, a minimal
        size of 10 MW drops the 5 MW fragment and spreads it over the other two::

            {1: 26.3, 2: 73.7}

        Raising the minimal size above 70 MW drops them all, leaving ``{1: 100}``.
        """
        volumes = {category: capacity * fragment.volume for category, fragment in self.fragment_data.items()}
        dropped = {category for category, volume in volumes.items() if volume < minimal_fragment_size}

        if sum(volumes[category] for category in dropped) <= 0:
            return volumes

        kept_capacity = sum(volume for category, volume in volumes.items() if category not in dropped)
        if kept_capacity == 0:
            return {math.ceil(len(volumes) / 2): capacity}
        return {
            category: capacity * volume / kept_capacity
            for category, volume in volumes.items()
            if category not in dropped
        }
