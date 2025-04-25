"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field

from atlas.math.forecasting_matrix import ForecastingMatrix
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
    :type stored_energy: ForecastingMatrix
    :param da_sell_submitted_volume: Sum of volume of sell offers for Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    :param energy_target: Target of storage capacity energy
    :type energy_target: Timeseries
    :param inflows: Inflows
    :type inflows: Timeseries
    :param initial_level: Energy contained in the hydraulic reservoir prior to execution of any ATLAS module
    :type initial_level: Timeseries
    :param maximum_energy: Maximum energy storage capacity
    :type maximum_energy: Timeseries
    :param minimum_energy: Minimum energy storage capacity
    :type minimum_energy: Timeseries
    :param maximum_power: Maximum power
    :type maximum_power: Timeseries
    :param minimum_power: Minimum power
    :type minimum_power: Timeseries
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

    stored_energy: ForecastingMatrix | None = None

    da_sell_submitted_volume: Timeseries | None = None
    energy_target: Timeseries | None = None
    inflows: Timeseries | None = None
    initial_level: Timeseries | None = None
    maximum_energy: Timeseries | None = None
    minimum_energy: Timeseries | None = None
    maximum_power: Timeseries | None = None
    minimum_power: Timeseries | None = None
