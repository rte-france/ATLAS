"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Self

from pydantic import model_validator

from atlas.common.optimal_dispatch.input_objects.storage import StorageDispatchInput
from atlas.enums import StorageType


class StorageDAO(StorageDispatchInput):
    @model_validator(mode="after")
    def validate_displacement_energy_for_ev(self) -> Self:
        """Ensure displacement_energy is filled for electric vehicle storage type."""
        if self.storage_type == StorageType.ELECTRIC_VEHICLE and self.displacement_energy is None:
            raise ValueError(f"displacement_energy is required for storage type {StorageType.ELECTRIC_VEHICLE.value}")
        return self
