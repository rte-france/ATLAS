"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pydantic import model_validator

from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput
from atlas.math.abstract_timeseries import AbstractTimeseries


class ThermalPO(ThermalDispatchInput):
    """
    Thermal power equipment data model for portfolio optimisation.
    """

    maximum_fcr: float
    maximum_afrr: float
    variable_cost: AbstractTimeseries
    maximum_gradient: float = 0.0
    has_daily_energy_constraint: bool = False

    @model_validator(mode="after")
    def validate_minimum_stable_power_duration(self) -> ThermalPO:
        """
        Validate that minimum_stable_power_duration is not greater than minimum_time_on.
        """
        if self.minimum_stable_power_duration > self.minimum_time_on:
            raise ValueError(
                f"minimum_stable_power_duration ({self.minimum_stable_power_duration.total_hours()}h) of equipment "
                f"{self.name} cannot be greater than minimum_time_on ({self.minimum_time_on.total_hours()}h)"
            )
        return self
