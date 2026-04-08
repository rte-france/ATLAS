"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Self

from pydantic import model_validator
from pydantic_extra_types.pendulum_dt import Duration

from atlas.enums import StorageType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.storage import Storage
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO


class StorageDAO(Storage):
    portfolio: PortfolioDAO
    maximum_energy: AbstractTimeseries
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    storage_initial_level: float
    minimum_state_of_charge: AbstractTimeseries
    additional_hours: Duration

    @model_validator(mode="after")
    def validate_displacement_energy_for_ev(self) -> Self:
        """Ensure displacement_energy is filled for electric vehicle storage type."""
        if self.storage_type == StorageType.ELECTRIC_VEHICLE and self.displacement_energy is None:
            raise ValueError(f"displacement_energy is required for storage type {StorageType.ELECTRIC_VEHICLE.value}")
        return self
