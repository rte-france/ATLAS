"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field

from atlas.config import StorageType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Storage(Equipment):
    """:param charge_efficiency: Effiency during charging phase. Corresponds to the ratio of energy stored in the
    battery to energy withdrawn from the system
    :type charge_efficiency: float
    :param discharge_efficiency: Effiency during discharge phase. Corresponds to the ratio of energy injected to the
    system to energy withdrawn from the battery
    :type discharge_efficiency: float
    :param is_v2g: True if Equipment has vehicule to grid capabilities
    :type is_v2g: bool
    :param storage_initial_level: Percentage of MaximumEnergy used as a reference to determine the unit's initial
    stock level, if StoredEnergy has not yet been filled by a previous market
    :type storage_initial_level: float
    :param storage_type: Sum of volume of sell offers on the Day Ahead market
    :type storage_type: StorageType
    :param transition_duration: Sum of volume of sell offers on the Day Ahead market
    :type transition_duration: float
    :param stored_energy: Portfolio Optimization output containing anticipated storage levels after each clearing
    :type stored_energy: ForecastingMatrix
    :param da_buy_submitted_volume: Sum of volume of purchase offers submitted to the Day Ahead market
    :type da_buy_submitted_volume: Timeseries
    :param da_sell_submitted_volume: Sum of volume of sell offers submitted to the Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    :param displacement_energy: Energy used by the connected electric vehicles since their last charge
    :type displacement_energy: Timeseries
    :param maximum_energy: Maximum energy that can be stored
    :type maximum_energy: Timeseries
    :param maximum_power: Sum of volume of sell offers on the Day Ahead market
    :type maximum_power: Timeseries
    :param minimum_power: Sum of volume of sell offers on the Day Ahead market
    :type minimum_power: Timeseries
    :param minimum_state_of_charge: Coefficient applied to MaximumEnergy, to represent the minimum energy that can be
    stored
    :type minimum_state_of_charge: Timeseries
    """

    charge_efficiency: float | None = Field(
        None,
        gt=0,
        description="Charge efficiency (must be positive)",
    )
    discharge_efficiency: float | None = Field(
        None,
        gt=0,
        description="Discharge efficiency (must be positive)",
    )
    is_v2g: bool | None = None
    storage_initial_level: float | None = Field(
        None,
        ge=0,
        description="Initial storage level (positive or zero)",
    )
    storage_type: StorageType | None = None
    transition_duration: float | None = Field(
        None,
        gt=0,
        description="Transition duration (must be positive)",
    )

    stored_energy: ForecastingMatrix | None = None

    da_buy_submitted_volume: Timeseries | None = None
    da_sell_submitted_volume: Timeseries | None = None
    displacement_energy: Timeseries | None = None
    maximum_energy: Timeseries | None = None
    maximum_power: Timeseries | None = None
    minimum_power: Timeseries | None = None
    minimum_state_of_charge: Timeseries | None = None
