"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import ConfigDict, Field

from atlas.config import StorageType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Storage(Equipment):
    """
    :param charge_efficiency: Installed capacity
    :type charge_efficiency: float
    :param discharge_efficiency: Sum of volume of sell offers on the Day Ahead market
    :type discharge_efficiency: float
    :param is_v2g: Equipment capping cost
    :type is_v2g: bool
    :param storage_initial_level: Stores capping at the end of each Portfolio Optimization
    :type storage_initial_level: float
    :param storage_type: Sum of volume of sell offers on the Day Ahead market
    :type storage_type: StorageType
    :param transition_duration: Sum of volume of sell offers on the Day Ahead market
    :type transition_duration: float
    :param stored_energy: Sum of volume of sell offers on the Day Ahead market
    :type stored_energy: ForecastingMatrix
    :param da_buy_submitted_volume: Sum of volume of sell offers on the Day Ahead market
    :type da_buy_submitted_volume: Timeseries
    :param da_sell_submitted_volume: Sum of volume of sell offers on the Day Ahead market
    :type da_sell_submitted_volume: Timeseries
    :param displacement_energy: Sum of volume of sell offers on the Day Ahead market
    :type displacement_energy: Timeseries
    :param maximum_energy: Sum of volume of sell offers on the Day Ahead market
    :type maximum_energy: Timeseries
    :param maximum_power: Sum of volume of sell offers on the Day Ahead market
    :type maximum_power: Timeseries
    :param minimum_power: Sum of volume of sell offers on the Day Ahead market
    :type minimum_power: Timeseries
    :param minimum_state_of_charge: Sum of volume of sell offers on the Day Ahead market
    :type minimum_state_of_charge: Timeseries
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
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
