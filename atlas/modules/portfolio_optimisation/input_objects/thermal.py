"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime
from pydantic import model_validator

from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.solver.model_var import ModelVar


class ThermalPO(ThermalDispatchInput):
    """
    Thermal power equipment data model for portfolio optimisation.
    """

    maximum_fcr: float
    maximum_afrr: float
    variable_cost: AbstractTimeseries
    maximum_gradient: float = 0.0
    has_daily_energy_constraint: bool = False
    optimisation_time_window: list[DateTime] = []

    _T_on: int = 0
    _T_off: int = 0
    _T_start: int = 0
    _T_stop: int = 0
    _T_stable: int = 0
    _Delta_Q: float = 0.0
    _Delta_Q_unconstrained: float = 0.0
    _combination: int = 1

    # ModelVar placeholders — set in _setup_state_variables
    off_var: ModelVar = None  # type: ignore[assignment]
    on_flat_var: ModelVar = None  # type: ignore[assignment]
    on_up_var: ModelVar = None  # type: ignore[assignment]
    on_down_var: ModelVar = None  # type: ignore[assignment]
    on_start_var: ModelVar = None  # type: ignore[assignment]
    entered_up_var: ModelVar = None  # type: ignore[assignment]
    entered_down_var: ModelVar = None  # type: ignore[assignment]
    stable_var: ModelVar = None  # type: ignore[assignment]
    flat_down_stop: ModelVar = None  # type: ignore[assignment]
    down_to_stop_grad: ModelVar = None  # type: ignore[assignment]
    stop_var: ModelVar = None  # type: ignore[assignment]
    turned_off: ModelVar = None  # type: ignore[assignment]
    turned_on: ModelVar = None  # type: ignore[assignment]
    power_level_var: ModelVar = None  # type: ignore[assignment]
    up_grad_var: ModelVar = None  # type: ignore[assignment]
    aux_up_grad_var: ModelVar = None  # type: ignore[assignment]
    down_grad_var: ModelVar = None  # type: ignore[assignment]
    aux_down_grad_var: ModelVar = None  # type: ignore[assignment]
    dd_grad_var: ModelVar = None  # type: ignore[assignment]

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
