"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Self

from pydantic import model_validator

from atlas.enums import StorageType
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.storage import Storage


class StorageDAO(Storage):
    maximum_energy: AbstractTimeseries
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    storage_initial_level: float
    minimum_state_of_charge: AbstractTimeseries
    optimization_additional_hours: AbstractScenarioMatrix

    @model_validator(mode="after")
    def validate_displacement_energy_for_ev(self) -> Self:
        """Ensure displacement_energy is filled for electric vehicle storage type."""
        if self.storage_type == StorageType.ELECTRIC_VEHICLE and self.displacement_energy is None:
            raise ValueError(f"displacement_energy is required for storage type {StorageType.ELECTRIC_VEHICLE.value}")
        return self
