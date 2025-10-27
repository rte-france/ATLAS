"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import duration
from pydantic import Field, computed_field, field_validator
from pydantic_extra_types.pendulum_dt import Duration

from atlas.enum import StorageType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment
from atlas.validators import hours_validator


class Storage(Equipment):
    """
    :param charge_efficiency: Effiency during charging phase. Corresponds to the ratio of energy stored in the
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
    :param storage_type: Storage type, e.g. battery, pumped hydro, etc.
    :type storage_type: StorageType
    :param transition_duration: Duration of the transition phase between two states (e.g. charging to discharging).
    :type transition_duration: Duration
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
    :param maximum_power: Maximum power of the unit or cluster
    :type maximum_power: Timeseries | LazyTimeseries
    :param minimum_power: Minimum power of the unit or cluster
    :type minimum_power: Timeseries
    :param minimum_state_of_charge: Coefficient applied to MaximumEnergy, to represent the minimum energy that can be
    stored
    :type minimum_state_of_charge: Timeseries

    """

    charge_efficiency: float | None = Field(
        None,
        ge=0,
        description="Charge efficiency (must be positive)",
    )
    discharge_efficiency: float | None = Field(
        None,
        ge=0,
        description="Discharge efficiency (must be positive)",
    )
    is_v2g: bool | None = None
    storage_initial_level: float | None = Field(
        None,
        ge=0,
        description="Initial storage level (positive or zero)",
    )
    storage_type: StorageType | None = None
    transition_duration: Duration | None = Field(
        None,
        description="Transition duration (must be positive)",
    )

    stored_energy: ForecastingMatrix | LazyForecastingMatrix | None = None

    da_buy_submitted_volume: Timeseries | LazyTimeseries | None = None
    da_sell_submitted_volume: Timeseries | LazyTimeseries | None = None
    displacement_energy: Timeseries | LazyTimeseries | None = None
    maximum_energy: Timeseries | LazyTimeseries | None = None
    maximum_power: Timeseries | LazyTimeseries | None = None
    minimum_power: Timeseries | LazyTimeseries | None = None
    minimum_state_of_charge: Timeseries | LazyTimeseries | None = None

    additional_hours_: Duration | None = Field(
        None,
        description="Optimization period in hours for hydraulic group.",
        alias="additional_hours",
    )

    @field_validator(
        "transition_duration",
        mode="before",
    )
    @classmethod
    def convert_hours_to_duration(cls, v):
        """Convert various duration formats to Duration objects."""
        return hours_validator(v)

    @computed_field
    @property
    def additional_hours(self) -> Duration:
        """Get additional hours for optimization period."""
        if self.additional_hours_ is None:
            if self.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
                return duration(hours=144)
            elif self.storage_type == StorageType.BATTERY:
                return duration(hours=48)
            if self.storage_type == StorageType.ELECTRIC_VEHICLE:
                return duration(hours=144)
        else:
            return self.additional_hours_
