"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Hydraulic(Equipment):
    """:param inflow_frequency: Frequency of inflow frequency information. "Monthly" for Antares 6 version and
    "daily" for Antares 7
    :type inflow_frequency: str
    :param energy_target_frequency: Frequency of energy target information. "Monthly" for Antares 6 version and
    "daily" for Antares 7
    :type energy_target_frequency: str
    :param fragment_prices: List of spreads applied to hydraulic equipment usage values, to assign prices to fragments
    calculated with FragmentVolumes
    :type fragment_prices: list[float]
    :param fragment_volumes: List of percentages used to divide the interval between MaximumPower and MinimumPower
    into different fragments
    :type fragment_volumes: list[float]
    :param stored_energy: Storage capacity of energy for different deadlines
    :type stored_energy: ForecastingMatrix | LazyForecastingMatrix
    :param da_sell_submitted_volume: Sum of volume of sell offers for Day Ahead market
    :type da_sell_submitted_volume: Timeseries | LazyTimeseries
    :param energy_target: Target of storage capacity energy
    :type energy_target: Timeseries | LazyTimeseries
    :param inflows: Inflows
    :type inflows: Timeseries | LazyTimeseries
    :param initial_level: Energy contained in the hydraulic reservoir prior to execution of any ATLAS module
    :type initial_level: Timeseries | LazyTimeseries
    :param maximum_energy: Maximum energy storage capacity
    :type maximum_energy: Timeseries | LazyTimeseries
    :param minimum_energy: Minimum energy storage capacity
    :type minimum_energy: Timeseries | LazyTimeseries
    :param maximum_power: Maximum power
    :type maximum_power: Timeseries | LazyTimeseries
    :param minimum_power: Minimum power
    :type minimum_power: Timeseries | LazyTimeseries
    """

    inflow_frequency: str | None = Field(None, description="Possible values: 'Monthly', 'Daily'")
    energy_target_frequency: str | None = Field(
        None,
        description="Possible values: 'Monthly', 'Daily'",
    )

    fragment_prices: list[float] | None = Field(
        None,
        description="List of positive prices",
    )
    fragment_volumes: list[float] | None = Field(None, description="List of positive volumes")

    stored_energy: ForecastingMatrix | LazyForecastingMatrix | None = None

    da_sell_submitted_volume: Timeseries | LazyTimeseries | None = None
    energy_target: Timeseries | LazyTimeseries | None = None
    inflows: Timeseries | LazyTimeseries | None = None
    initial_level: Timeseries | LazyTimeseries | None = None
    maximum_energy: Timeseries | LazyTimeseries | None = None
    minimum_energy: Timeseries | LazyTimeseries | None = None
    maximum_power: Timeseries | LazyTimeseries | None = None
    minimum_power: Timeseries | LazyTimeseries | None = None
