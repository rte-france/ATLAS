"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations
from dataclasses import dataclass
from plotly import data
from atlas.abstract_class.parameters import AbstractModuleParameters

import math
from typing import TYPE_CHECKING

from pendulum import DateTime, Duration

from atlas.common.optimal_dispatch.dispatch.thermal_initial_conditions import ThermalInitialConditions
from atlas.math.timeseries import Timeseries
from atlas.solver.model_var import ModelVar
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput

@dataclass
class _ThermalDispatchParameters:
    """Minimal temporal parameter surface consumed by ThermalDispatch."""

    timestep: Duration
    start_date: DateTime
    end_date: DateTime
    execution_date: DateTime


class ThermalDispatch:
    """
    Physical dispatch component for a single thermal unit.

    Owns all model variables and physical constraints (combinations 1–8).
    Does **not** handle reserves, fill-up constraints, or objective terms —
    those remain module-specific.

    Typical usage::

        dispatch = ThermalDispatch(equipment)
        dispatch.setup(model, parameters)                 # init vars + initial conditions
        for time in time_window:
            dispatch.add_variables(time)                  # per-timestep decision variables
        for time in time_window:
            dispatch.add_constraints(model, time, parameters)
    """

    def __init__(self, equipment: ThermalDispatchInput) -> None:
        self._eq = equipment

        # Time parameters — populated by setup()
        self._T_on: int = 0
        self._T_off: int = 0
        self._T_start: int = 0
        self._T_stop: int = 0
        self._T_stable: int = 0
        self._Delta_Q: float = 0.0
        self._Delta_Q_unconstrained: float = 0.0
        self._combination: int = 1

        # Booleans derived from T params — set after _compute_time_parameters
        self._has_stop: bool = False
        self._has_start: bool = False
        self._has_flat: bool = False

        # ModelVar placeholders — populated by _setup_state_variables()
        self.off_var: ModelVar = None  # type: ignore[assignment]
        self.on_flat_var: ModelVar = None  # type: ignore[assignment]
        self.on_up_var: ModelVar = None  # type: ignore[assignment]
        self.on_down_var: ModelVar = None  # type: ignore[assignment]
        self.on_start_var: ModelVar = None  # type: ignore[assignment]
        self.entered_up_var: ModelVar = None  # type: ignore[assignment]
        self.entered_down_var: ModelVar = None  # type: ignore[assignment]
        self.stable_var: ModelVar = None  # type: ignore[assignment]
        self.flat_down_stop: ModelVar = None  # type: ignore[assignment]
        self.down_to_stop_grad: ModelVar = None  # type: ignore[assignment]
        self.stop_var: ModelVar = None  # type: ignore[assignment]
        self.turned_off: ModelVar = None  # type: ignore[assignment]
        self.turned_on: ModelVar = None  # type: ignore[assignment]
        self.power_level_var: ModelVar = None  # type: ignore[assignment]
        self.up_grad_var: ModelVar = None  # type: ignore[assignment]
        self.aux_up_grad_var: ModelVar = None  # type: ignore[assignment]
        self.down_grad_var: ModelVar = None  # type: ignore[assignment]
        self.aux_down_grad_var: ModelVar = None  # type: ignore[assignment]
        self.dd_grad_var: ModelVar = None  # type: ignore[assignment]

    # ── Public API ────────────────────────────────────────────────────────

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters) -> None:
        """
        Compute time parameters, create ModelVar objects, and apply initial conditions.

        Must be called before :meth:`add_variables` or :meth:`add_constraints`.

        :param model: The optimisation model
        :param parameters: Module parameters — must expose ``temporal.timestep``,
            ``temporal.start_date``, ``temporal.end_date``, ``temporal.execution_date``
        """
        self._compute_time_parameters(parameters)
        self._setup_state_variables(model)
        self._add_initial_variables(parameters)
        self._add_initial_conditions(parameters)

    def add_variables(self, time: DateTime) -> None:
        """
        Register decision variables for *time* in the model.

        :param time: The timestep for which to create variables
        :type time: DateTime
        """
        self.off_var.set_model_var(time)
        self.on_up_var.set_model_var(time)
        self.on_down_var.set_model_var(time)
        self.turned_on.set_model_var(time)
        self.turned_off.set_model_var(time)

        if self._T_start >= 1:
            self.on_start_var.set_model_var(time)
        if self._T_stop >= 1:
            self.stop_var.set_model_var(time)
        if self._T_stable >= 1:
            self.on_flat_var.set_model_var(time)
            self.stable_var.set_model_var(time)
            self.entered_up_var.set_model_var(time)
            self.entered_down_var.set_model_var(time)
            self.up_grad_var.set_model_var(time)
            self.aux_up_grad_var.set_model_var(time)
            self.down_grad_var.set_model_var(time)
            self.aux_down_grad_var.set_model_var(time)
        if self._T_stop >= 1 and self._T_start == 0 and self._T_stable == 0:
            self.down_to_stop_grad.set_model_var(time)
        if self._T_stop >= 1 and self._T_stable >= 1:
            self.flat_down_stop.set_model_var(time)
        if self._T_stable >= 1 and (self._T_start >= 1 or self._T_stop >= 1):
            self.dd_grad_var.set_model_var(time)
        if self._T_stop >= 1 and self._T_start >= 1 and self._T_stable == 0:
            self.down_to_stop_grad.set_model_var(time)

        self.power_level_var.set_model_var(time)

    def add_constraints(self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters) -> None:
        """
        Add all physical constraints for *time*.

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param parameters: Module parameters
        """
        ts = parameters.temporal.timestep
        prev_time = time - ts

        self._add_turned_on(model, time, prev_time)
        self._add_turned_off(model, time, prev_time)

        if self._has_flat:
            self._add_stable(model, time, prev_time)
            if self._has_stop:
                self._add_flat_down_stop(model, time, prev_time, ts)
            self._add_entered_up_down(model, time, prev_time)
            self._add_gradient_auxiliaries(model, time, prev_time)

        if self._has_stop and not self._has_flat:
            self._add_down_to_stop_evol(model, time, prev_time)

        self._add_mutual_exclusion(model, time)

        if self._has_flat and time == parameters.temporal.start_date:  # type: ignore[attr-defined]
            self._add_initial_boundary_constraints(model, time, prev_time, ts)

        self._add_transition_constraints(model, time, prev_time)
        self._add_eviction_constraints(model, time, parameters)
        self._add_minimum_time_constraints(model, time, parameters)
        self._add_power_bounds(model, time)

    def add_dd_and_gradient_constraints(
        self, model: OptimisationModel, time: DateTime, prev_time: DateTime
    ) -> None:
        """
        Add DD auxiliary and gradient constraints for *time*.

        Must only be called when *time* is not among the last two steps of the window.

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param prev_time: Previous timestep
        :type prev_time: DateTime
        """
        if self._has_flat and self._has_stop:
            self._add_dd_constraints(model, time, prev_time)
        self._add_gradient_constraints(model, time, prev_time)

    # ── Public accessors (combination / flags) ────────────────────────────

    @property
    def combination(self) -> int:
        return self._combination

    @property
    def name(self) -> str:
        return self._eq.name

    # ── Initialisation ────────────────────────────────────────────────────

    def _compute_time_parameters(self, parameters: object) -> None:
        eq = self._eq
        temporal = parameters.temporal  # type: ignore[attr-defined]
        ts = temporal.timestep

        self._T_on = (
            int(max(1, math.ceil(eq.minimum_time_on / ts))) + 1
            if eq.minimum_time_on and eq.minimum_time_on.total_minutes() > 0
            else 0
        )
        self._T_off = (
            int(max(1, math.ceil(eq.minimum_time_off / ts))) + 1
            if eq.minimum_time_off and eq.minimum_time_off.total_minutes() > 0
            else 0
        )
        self._T_start = int(math.floor(eq.startup_duration / ts)) if eq.startup_duration else 0
        self._T_stop = int(math.floor(eq.shutdown_duration / ts)) if eq.shutdown_duration else 0

        if eq.minimum_stable_power_duration:
            if eq.minimum_stable_power_duration < ts:
                self._T_stable = 0
            else:
                t = int(math.ceil(eq.minimum_stable_power_duration / ts)) + 1
                self._T_stable = t if t >= 2 else 0
        else:
            self._T_stable = 0

        max_grad = getattr(eq, "maximum_gradient", 0.0) or 0.0
        self._Delta_Q = max_grad * ts.total_minutes()
        self._Delta_Q_unconstrained = eq.maximum_power.slice(
            temporal.start_date, temporal.end_date, inplace=False
        ).max()

        self._has_stop = self._T_stop >= 1
        self._has_start = self._T_start >= 1
        self._has_flat = self._T_stable >= 1
        self._combination = self._determine_combination()

    def _determine_combination(self) -> int:
        s, st, f = self._has_stop, self._has_start, self._has_flat
        if not s and not st and not f:
            return 1
        elif s and not st and not f:
            return 2
        elif not s and not st and f:
            return 3
        elif not s and st and not f:
            return 4
        elif s and not st and f:
            return 5
        elif not s and st and f:
            return 6
        elif s and st and not f:
            return 7
        else:
            return 8

    def _setup_state_variables(self, model: OptimisationModel) -> None:
        eq = self._eq
        n = eq.name

        self.off_var = ModelVar(
            getter=lambda time: model.get_variable(f"off_{n}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"off_{n}_{time}"),
        )
        self.on_flat_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_flat_{n}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_flat_{n}_{time}"),
        )
        self.on_up_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_up_{n}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_up_{n}_{time}"),
        )
        self.on_down_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_down_{n}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_down_{n}_{time}"),
        )
        self.on_start_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_start_{n}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_start_{n}_{time}"),
        )
        self.entered_up_var = ModelVar(
            getter=lambda time: model.get_variable(f"entered_up_{time}_{n}"),
            setter=lambda time: model.add_boolean_variable(f"entered_up_{time}_{n}"),
        )
        self.entered_down_var = ModelVar(
            getter=lambda time: model.get_variable(f"entered_down_{time}_{n}"),
            setter=lambda time: model.add_boolean_variable(f"entered_down_{time}_{n}"),
        )
        self.stable_var = ModelVar(
            getter=lambda time: model.get_variable(f"stable_{time}_{n}"),
            setter=lambda time: model.add_boolean_variable(f"stable_{time}_{n}"),
        )
        self.flat_down_stop = ModelVar(
            getter=lambda time: model.get_variable(f"flat_down_stop_{time}_{n}"),
            setter=lambda time: model.add_boolean_variable(f"flat_down_stop_{time}_{n}"),
        )
        self.down_to_stop_grad = ModelVar(
            getter=lambda time: model.get_variable(f"down_to_stop_grad_{time}_{n}"),
            setter=lambda time: model.add_boolean_variable(f"down_to_stop_grad_{time}_{n}"),
        )
        self.stop_var = ModelVar(
            getter=lambda time: model.get_variable(f"stop_{n}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"stop_{n}_{time}"),
        )
        self.turned_off = ModelVar(
            getter=lambda time: model.get_variable(f"t_off_{n}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"t_off_{n}_{time}"),
        )
        self.turned_on = ModelVar(
            getter=lambda time: model.get_variable(f"t_on_{n}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"t_on_{n}_{time}"),
        )
        self.power_level_var = ModelVar(
            getter=lambda time: model.get_variable(f"{n}_power_level_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{n}_power_level_{time}", 0, eq.maximum_power.get_value(time)
            ),
        )
        self.up_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"up_grad_{time}_{n}"),
            setter=lambda time: model.add_continuous_variable(
                f"up_grad_{time}_{n}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )
        self.down_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"down_grad_{time}_{n}"),
            setter=lambda time: model.add_continuous_variable(
                f"down_grad_{time}_{n}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )
        self.aux_up_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"aux_up_grad_{time}_{n}"),
            setter=lambda time: model.add_continuous_variable(
                f"aux_up_grad_{time}_{n}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )
        self.aux_down_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"aux_down_grad_{time}_{n}"),
            setter=lambda time: model.add_continuous_variable(
                f"aux_down_grad_{time}_{n}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )
        self.dd_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"dd_grad_{time}_{n}"),
            setter=lambda time: model.add_continuous_variable(
                f"dd_grad_{time}_{n}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )

    def _add_initial_variables(self, parameters: AbstractModuleParameters) -> None:
        temporal = parameters.temporal
        prev = temporal.start_date - temporal.timestep
        if self._T_stable >= 1:
            self.on_up_var.set_model_var(prev)
            self.on_down_var.set_model_var(prev)
            self.on_flat_var.set_model_var(prev)
            self.stable_var.set_model_var(prev)
            self.entered_up_var.set_model_var(prev)
            self.entered_down_var.set_model_var(prev)
        if self._T_stable >= 1 and (self._T_start >= 1 or self._T_stop >= 1):
            self.dd_grad_var.set_model_var(prev)

    # ── Initial conditions ────────────────────────────────────────────────

    def _add_initial_conditions(self, parameters: AbstractModuleParameters) -> None:
        ic = self._build_initial_conditions(parameters)
        if ic.day_zero:
            self._init_day_zero(parameters, ic)
        else:
            self._init_from_previous(parameters, ic)

    def _build_initial_conditions(self, parameters: AbstractModuleParameters) -> ThermalInitialConditions:
        eq = self._eq
        temporal = parameters.temporal  # type: ignore[attr-defined]
        T_traceback = max(self._T_on + self._T_start, self._T_off + self._T_stop)

        initial_times: list[DateTime] = []
        stable_initial_times: list[DateTime] = []
        if T_traceback > 0:
            for k in range(T_traceback, 0, -1):
                initial_times.append(temporal.start_date - k * temporal.timestep)
        else:
            initial_times.append(temporal.start_date - temporal.timestep)
        for k in range(T_traceback, 1, -1):
            stable_initial_times.append(temporal.start_date - k * temporal.timestep)

        power_ts = (
            eq.power.get_forecast(temporal.execution_date, initial_times[0], initial_times[-1])
            if eq.power is not None
            else None
        )

        day_zero = power_ts is None
        if power_ts is not None:
            if temporal.start_date - temporal.timestep != power_ts.last_date():
                day_zero = True

        return ThermalInitialConditions(
            initial_times=initial_times,
            stable_initial_times=stable_initial_times,
            power_ts=power_ts,
            day_zero=day_zero,
        )

    def _init_day_zero(self, parameters: AbstractModuleParameters, ic: ThermalInitialConditions) -> None:
        for time in ic.initial_times:
            self._init_day_zero_core(time)
            if not self._has_flat:
                self._init_day_zero_on_states(time)
            else:
                self._init_day_zero_gradient_vars(time)
            if self._has_stop:
                self.stop_var.set_extended(time, 0)
                if not self._has_flat:
                    self.down_to_stop_grad.set_extended(time, 0)
                else:
                    self.flat_down_stop.set_extended(time, 0)
            if self._has_start:
                self.on_start_var.set_extended(time, 0)

        for time in ic.stable_initial_times:
            self._init_day_zero_stable_vars(time)

        if self._has_flat and not self._has_stop and not self._has_start:
            if isinstance(ic.power_ts, Timeseries):
                self._init_gradient_initial_conditions(parameters)

    def _init_from_previous(self, parameters: AbstractModuleParameters, ic: ThermalInitialConditions) -> None:
        if not isinstance(ic.power_ts, Timeseries):
            raise ValueError("power_ts is required when day_zero is False")

        for time in ic.initial_times:
            self._init_one_time(parameters, ic.extended_start_date, time, ic.power_ts)

        if self._has_flat:
            self._init_stable_times(parameters, ic)
            self._init_gradient_initial_conditions(parameters)
            if self._has_stop:
                self._init_flat_down_stop(parameters, ic)

    def _init_one_time(
        self,
        parameters: AbstractModuleParameters,
        extended_start_date: DateTime,
        time: DateTime,
        power_ts: Timeseries,
    ) -> None:
        ts = parameters.temporal.timestep  # type: ignore[attr-defined]
        if time in power_ts:
            power_t = power_ts.get_value(time)
            self.power_level_var.set_extended(time, power_t)

            if self._has_start or self._has_stop:
                min_power = self._eq.minimum_power.get_value(time)
                if power_t >= min_power:
                    self.off_var.set_extended(time, 0)
                    if self._has_stop:
                        self.stop_var.set_extended(time, 0)
                    if self._has_start:
                        self.on_start_var.set_extended(time, 0)
                    if not self._has_flat:
                        self.on_up_var.set_extended(time, 1)
                        self.on_down_var.set_extended(time, 1)
                elif power_t > 0:
                    self.off_var.set_extended(time, 0)
                    if self._has_stop:
                        self.stop_var.set_extended(time, 1)
                    if self._has_start:
                        self.on_start_var.set_extended(time, 1)
                    if not self._has_flat:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 0)
                else:
                    self.off_var.set_extended(time, 1)
                    if self._has_stop:
                        self.stop_var.set_extended(time, 0)
                    if self._has_start:
                        self.on_start_var.set_extended(time, 0)
                    if not self._has_flat:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 0)
            else:
                if power_t > 0:
                    self.off_var.set_extended(time, 0)
                    if not self._has_flat:
                        self.on_up_var.set_extended(time, 1)
                        self.on_down_var.set_extended(time, 0)
                else:
                    self.power_level_var.set_extended(time, 0)
                    self.off_var.set_extended(time, 1)
                    if not self._has_flat:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 0)
        else:
            self.power_level_var.set_extended(time, 0)
            self.off_var.set_extended(time, 1)
            if self._has_stop:
                self.stop_var.set_extended(time, 0)
            if self._has_start:
                self.on_start_var.set_extended(time, 0)
            if not self._has_flat:
                self.on_up_var.set_extended(time, 0)
                self.on_down_var.set_extended(time, 0)

        self.turned_on.set_extended(time, 0)
        self.turned_off.set_extended(time, 0)
        if self._has_stop and not self._has_flat:
            self.down_to_stop_grad.set_extended(time, 0)

        if time == extended_start_date:
            return

        prev_time = time - ts

        if self._has_start and self._has_stop and time in power_ts:
            power_t = power_ts.get_value(time)
            prev_power = power_ts.get_value(prev_time) if prev_time in power_ts else 0
            if self.on_start_var.get_extended_value(time) == 1:
                if power_t > prev_power:
                    self.stop_var.set_extended(time, 0)
                elif power_t < prev_power:
                    self.stop_var.set_extended(time, 1)
                    self.on_start_var.set_extended(time, 0)

        if self._has_stop:
            if self.stop_var.get_extended_value(time) - self.stop_var.get_extended_value(prev_time) == 1:
                self.turned_off.set_extended(time, 1)
        else:
            if self.off_var.get_extended_value(time) - self.off_var.get_extended_value(prev_time) == 1:
                self.turned_off.set_extended(time, 1)

        if self._has_start:
            if self.on_start_var.get_extended_value(time) - self.on_start_var.get_extended_value(prev_time) == 1:
                self.turned_on.set_extended(time, 1)
        else:
            if self.off_var.get_extended_value(time) - self.off_var.get_extended_value(prev_time) == -1:
                self.turned_on.set_extended(time, 1)

        if self._has_stop and not self._has_flat:
            if self.stop_var.get_extended_value(time) - self.on_down_var.get_extended_value(prev_time) == 0:
                self.down_to_stop_grad.set_extended(time, 1)

    def _init_stable_times(self, parameters: AbstractModuleParameters, ic: ThermalInitialConditions) -> None:
        ts = parameters.temporal.timestep  # type: ignore[attr-defined]
        for time in ic.stable_initial_times:
            next_time = time + ts
            current_power = self.power_level_var.get_extended_value(time)
            next_power = self.power_level_var.get_extended_value(next_time)

            self.stable_var.set_extended(time, 0)
            self.entered_up_var.set_extended(time, 0)
            self.entered_down_var.set_extended(time, 0)

            if self.off_var.get_extended_value(time) == 0:
                in_ramp = (self._has_stop and self.stop_var.get_extended_value(time) == 1) or (
                    self._has_start and self.on_start_var.get_extended_value(time) == 1
                )
                if in_ramp:
                    self.on_up_var.set_extended(time, 0)
                    self.on_down_var.set_extended(time, 0)
                    self.on_flat_var.set_extended(time, 0)
                else:
                    if current_power < next_power:
                        self.on_up_var.set_extended(time, 1)
                        self.on_down_var.set_extended(time, 0)
                        self.on_flat_var.set_extended(time, 0)
                    elif current_power > next_power:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 1)
                        self.on_flat_var.set_extended(time, 0)
                    else:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 0)
                        self.on_flat_var.set_extended(time, 1)
            else:
                self.on_up_var.set_extended(time, 0)
                self.on_down_var.set_extended(time, 0)
                self.on_flat_var.set_extended(time, 0)

            if time != ic.extended_start_date and self.off_var.get_extended_value(time) != 1:
                prev_time = time - ts
                if self.on_flat_var.get_extended_value(time) - self.on_flat_var.get_extended_value(prev_time) == 1:
                    self.stable_var.set_extended(time, 1)
                if self.on_up_var.get_extended_value(time) - self.on_up_var.get_extended_value(prev_time) == 1:
                    self.entered_up_var.set_extended(time, 1)
                if self.on_down_var.get_extended_value(time) - self.on_down_var.get_extended_value(prev_time) == 1:
                    self.entered_down_var.set_extended(time, 1)

    def _init_flat_down_stop(self, parameters: AbstractModuleParameters, ic: ThermalInitialConditions) -> None:
        ts = parameters.temporal.timestep  # type: ignore[attr-defined]
        start_date = parameters.temporal.start_date  # type: ignore[attr-defined]
        for idx, time in enumerate(ic.stable_initial_times):
            if idx >= 2:
                self._set_flat_down_stop(time, time - ts, time - 2 * ts)
        self._set_flat_down_stop(
            start_date - ts,
            start_date - 2 * ts,
            start_date - 3 * ts,
        )

    def _set_flat_down_stop(self, time: DateTime, time_minus_one: DateTime, time_minus_two: DateTime) -> None:
        self.flat_down_stop.set_extended(
            time,
            (
                self.stop_var.get_extended_value(time)
                + self.on_down_var.get_extended_value(time_minus_one)
                + self.on_flat_var.get_extended_value(time_minus_two)
            )
            / 3,
        )

    def _init_gradient_initial_conditions(self, parameters: AbstractModuleParameters) -> None:
        temporal = parameters.temporal  # type: ignore[attr-defined]
        t_minus_one = temporal.start_date - temporal.timestep
        t_minus_two = temporal.start_date - 2 * temporal.timestep

        power_minus_one = self.power_level_var.get_value(t_minus_one)
        power_minus_two = self.power_level_var.get_value(t_minus_two)
        power_diff = power_minus_one - power_minus_two

        self.up_grad_var.set_extended(
            t_minus_one,
            power_diff
            * self.on_up_var.get_value(t_minus_one)
            * self.on_up_var.get_value(t_minus_two),
        )
        self.down_grad_var.set_extended(
            t_minus_one,
            power_diff
            * self.on_down_var.get_value(t_minus_one)
            * self.on_down_var.get_value(t_minus_two),
        )

    # ── Day-zero helpers ──────────────────────────────────────────────────

    def _init_day_zero_core(self, time: DateTime) -> None:
        self.off_var.set_extended(time, 1)
        self.turned_on.set_extended(time, 0)
        self.turned_off.set_extended(time, 0)
        self.power_level_var.set_extended(time, 0)

    def _init_day_zero_on_states(self, time: DateTime) -> None:
        self.on_up_var.set_extended(time, 0)
        self.on_down_var.set_extended(time, 0)

    def _init_day_zero_gradient_vars(self, time: DateTime) -> None:
        self.up_grad_var.set_extended(time, 0)
        self.down_grad_var.set_extended(time, 0)
        self.aux_up_grad_var.set_extended(time, 0)
        self.aux_down_grad_var.set_extended(time, 0)

    def _init_day_zero_stable_vars(self, time: DateTime) -> None:
        self.on_flat_var.set_extended(time, 0)
        self.on_up_var.set_extended(time, 0)
        self.on_down_var.set_extended(time, 0)
        self.stable_var.set_extended(time, 0)
        self.entered_up_var.set_extended(time, 0)
        self.entered_down_var.set_extended(time, 0)

    # ── Constraints ───────────────────────────────────────────────────────

    def _add_turned_on(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        ton = self.turned_on.get_value(time)
        off = self.off_var.get_value(time)
        off_prev = self.off_var.get_value(prev_time)
        n = self._eq.name
        model.add_constraint(ton <= 1 - off, f"t_on_evol_1_{time}_{n}")
        model.add_constraint(ton <= off_prev, f"t_on_evol_2_{time}_{n}")
        model.add_constraint(ton >= off_prev - off, f"t_on_evol_3_{time}_{n}")

    def _add_turned_off(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        toff = self.turned_off.get_value(time)
        n = self._eq.name
        if self._has_stop:
            stop = self.stop_var.get_value(time)
            stop_prev = self.stop_var.get_value(prev_time)
            model.add_constraint(toff <= 1 - stop_prev, f"t_off_evol_1_{time}_{n}")
            model.add_constraint(toff <= stop, f"t_off_evol_2_{time}_{n}")
            model.add_constraint(toff >= stop - stop_prev, f"t_off_evol_3_{time}_{n}")
        else:
            off = self.off_var.get_value(time)
            off_prev = self.off_var.get_value(prev_time)
            model.add_constraint(toff <= 1 - off_prev, f"t_off_evol_1_{time}_{n}")
            model.add_constraint(toff <= off, f"t_off_evol_2_{time}_{n}")
            model.add_constraint(toff >= off - off_prev, f"t_off_evol_3_{time}_{n}")

    def _add_stable(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        stab = self.stable_var.get_value(time)
        flat = self.on_flat_var.get_value(time)
        flat_prev = self.on_flat_var.get_value(prev_time)
        n = self._eq.name
        model.add_constraint(stab <= 1 - flat_prev, f"stable_evol_1_{time}_{n}")
        model.add_constraint(stab <= flat, f"stable_evol_2_{time}_{n}")
        model.add_constraint(stab >= flat - flat_prev, f"stable_evol_3_{time}_{n}")

    def _add_flat_down_stop(
        self, model: OptimisationModel, time: DateTime, prev_time: DateTime, ts: Duration
    ) -> None:
        fds = self.flat_down_stop.get_value(time)
        stop = self.stop_var.get_value(time)
        on_down_prev = self.on_down_var.get_value(prev_time)
        flat_prev2 = self.on_flat_var.get_value(prev_time - ts)  # type: ignore[operator]
        n = self._eq.name
        prefix = "flat_down_stop_evol" if not self._has_start else "flat_down_stop"
        model.add_constraint(fds <= stop, f"{prefix}_1_{time}_{n}")
        model.add_constraint(fds <= on_down_prev, f"{prefix}_2_{time}_{n}")
        model.add_constraint(fds <= flat_prev2, f"{prefix}_3_{time}_{n}")
        model.add_constraint(fds >= stop + on_down_prev + flat_prev2 - 2, f"{prefix}_4_{time}_{n}")

    def _add_entered_up_down(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        eu = self.entered_up_var.get_value(time)
        on_up = self.on_up_var.get_value(time)
        on_up_prev = self.on_up_var.get_value(prev_time)
        ed = self.entered_down_var.get_value(time)
        on_down = self.on_down_var.get_value(time)
        on_down_prev = self.on_down_var.get_value(prev_time)
        n = self._eq.name
        model.add_constraint(eu <= 1 - on_up_prev, f"entered_up_evol_1_{time}_{n}")
        model.add_constraint(eu <= on_up, f"entered_up_evol_2_{time}_{n}")
        model.add_constraint(eu >= on_up - on_up_prev, f"entered_up_evol_3_{time}_{n}")
        model.add_constraint(ed <= 1 - on_down_prev, f"entered_down_evol_1_{time}_{n}")
        model.add_constraint(ed <= on_down, f"entered_down_evol_2_{time}_{n}")
        model.add_constraint(ed >= on_down - on_down_prev, f"entered_down_evol_3_{time}_{n}")

    def _add_gradient_auxiliaries(
        self, model: OptimisationModel, time: DateTime, prev_time: DateTime
    ) -> None:
        n = self._eq.name
        max_p = self._eq.maximum_power.get_value(time)
        min_p = -max_p
        power = self.power_level_var.get_value(time)
        power_prev = self.power_level_var.get_value(prev_time)
        dq = power - power_prev

        on_up_prev = self.on_up_var.get_value(prev_time)
        on_down_prev = self.on_down_var.get_value(prev_time)
        on_up = self.on_up_var.get_value(time)
        on_down = self.on_down_var.get_value(time)
        aux_u = self.aux_up_grad_var.get_value(time)
        aux_d = self.aux_down_grad_var.get_value(time)
        u = self.up_grad_var.get_value(time)
        d = self.down_grad_var.get_value(time)

        model.add_constraint(aux_u <= max_p * on_up_prev, f"tilde_U_evol_1_{time}_{n}")
        model.add_constraint(aux_u >= min_p * on_up_prev, f"tilde_U_evol_2_{time}_{n}")
        model.add_constraint(aux_u <= dq - min_p * (1 - on_up_prev), f"tilde_U_evol_3_{time}_{n}")
        model.add_constraint(aux_u >= dq - max_p * (1 - on_up_prev), f"tilde_U_evol_4_{time}_{n}")
        model.add_constraint(aux_d <= max_p * on_down_prev, f"tilde_D_evol_1_{time}_{n}")
        model.add_constraint(aux_d >= min_p * on_down_prev, f"tilde_D_evol_2_{time}_{n}")
        model.add_constraint(aux_d <= dq - min_p * (1 - on_down_prev), f"tilde_D_evol_3_{time}_{n}")
        model.add_constraint(aux_d >= dq - max_p * (1 - on_down_prev), f"tilde_D_evol_4_{time}_{n}")
        model.add_constraint(u <= max_p * on_up, f"U_evol_1_{time}_{n}")
        model.add_constraint(u >= min_p * on_up, f"U_evol_2_{time}_{n}")
        model.add_constraint(u <= aux_u - min_p * (1 - on_up), f"U_evol_3_{time}_{n}")
        model.add_constraint(u >= aux_u - max_p * (1 - on_up), f"U_evol_4_{time}_{n}")
        model.add_constraint(d <= max_p * on_down, f"D_evol_1_{time}_{n}")
        model.add_constraint(d >= min_p * on_down, f"D_evol_2_{time}_{n}")
        model.add_constraint(d <= aux_d - min_p * (1 - on_down), f"D_evol_3_{time}_{n}")
        model.add_constraint(d >= aux_d - max_p * (1 - on_down), f"D_evol_4_{time}_{n}")

    def _add_down_to_stop_evol(
        self, model: OptimisationModel, time: DateTime, prev_time: DateTime
    ) -> None:
        n = self._eq.name
        dts = self.down_to_stop_grad.get_value(time)
        on_down = self.on_down_var.get_value(time)
        on_down_prev = self.on_down_var.get_value(prev_time)
        if self._has_start:
            stop = self.stop_var.get_value(time)
            model.add_constraint(dts <= stop, f"down_to_stop_evol_1_{time}_{n}")
            model.add_constraint(dts <= on_down_prev, f"down_to_stop_evol_2_{time}_{n}")
            model.add_constraint(dts >= stop + on_down_prev - 1, f"down_to_stop_evol_3_{time}_{n}")
        else:
            model.add_constraint(dts <= 1 - on_down_prev, f"t_stop_evol_1_{time}_{n}")
            model.add_constraint(dts <= on_down, f"t_stop_evol_2_{time}_{n}")
            model.add_constraint(dts >= on_down - on_down_prev, f"t_stop_evol_3_{time}_{n}")

    def _add_mutual_exclusion(self, model: OptimisationModel, time: DateTime) -> None:
        n = self._eq.name
        expr = self.off_var.get_value(time) + self.on_up_var.get_value(time) + self.on_down_var.get_value(time)
        if self._has_flat:
            expr = expr + self.on_flat_var.get_value(time)
        if self._has_stop:
            expr = expr + self.stop_var.get_value(time)
        if self._has_start:
            expr = expr + self.on_start_var.get_value(time)
        model.add_constraint(expr == 1, f"mutual_exclusion_{time}_{n}")

    def _add_initial_boundary_constraints(
        self, model: OptimisationModel, time: DateTime, prev_time: DateTime, ts: Duration
    ) -> None:
        n = self._eq.name
        prev2 = prev_time - ts  # type: ignore[operator]

        on_flat_prev = self.on_flat_var.get_value(prev_time)
        on_flat_prev2 = self.on_flat_var.get_value(prev2)
        on_up_prev = self.on_up_var.get_value(prev_time)
        on_up_prev2 = self.on_up_var.get_value(prev2)
        on_down_prev = self.on_down_var.get_value(prev_time)
        on_down_prev2 = self.on_down_var.get_value(prev2)
        stable_prev = self.stable_var.get_value(prev_time)
        entered_up_prev = self.entered_up_var.get_value(prev_time)
        entered_down_prev = self.entered_down_var.get_value(prev_time)

        if self._has_stop and self._has_start:
            model.add_constraint(stable_prev <= on_flat_prev2, f"stable_evol_1_{prev_time}_{n}")
        else:
            model.add_constraint(stable_prev <= 1 - on_flat_prev2, f"stable_evol_1_{prev_time}_{n}")
        model.add_constraint(stable_prev <= on_flat_prev, f"stable_evol_2_{prev_time}_{n}")
        model.add_constraint(stable_prev >= on_flat_prev - on_flat_prev2, f"stable_evol_3_{prev_time}_{n}")

        model.add_constraint(entered_up_prev <= 1 - on_up_prev2, f"entered_up_evol_1_{prev_time}_{n}")
        model.add_constraint(entered_up_prev <= on_up_prev, f"entered_up_evol_2_{prev_time}_{n}")
        model.add_constraint(entered_up_prev >= on_up_prev - on_up_prev2, f"entered_up_evol_3_{prev_time}_{n}")
        model.add_constraint(entered_down_prev <= 1 - on_down_prev2, f"entered_down_evol_1_{prev_time}_{n}")
        model.add_constraint(entered_down_prev <= on_down_prev, f"entered_down_evol_2_{prev_time}_{n}")
        model.add_constraint(entered_down_prev >= on_down_prev - on_down_prev2, f"entered_down_evol_3_{prev_time}_{n}")

        expr_prev = self.off_var.get_value(prev_time) + on_up_prev + on_down_prev + on_flat_prev
        if self._has_stop:
            expr_prev = expr_prev + self.stop_var.get_value(prev_time)
        if self._has_start:
            expr_prev = expr_prev + self.on_start_var.get_value(prev_time)
        model.add_constraint(expr_prev == 1, f"mutual_exclusion_{prev_time}_{n}")

        model.add_constraint(on_up_prev2 + on_down_prev <= 1, f"transition_constraint_1_{prev_time}_{n}")
        model.add_constraint(on_down_prev2 + on_up_prev <= 1, f"transition_constraint_2_{prev_time}_{n}")
        if self._has_stop:
            stop_prev2 = self.stop_var.get_value(prev2)
            base = 3 if self._has_start else 5
            model.add_constraint(stop_prev2 + on_flat_prev <= 1, f"transition_constraint_{base}_{prev_time}_{n}")
            model.add_constraint(stop_prev2 + on_down_prev <= 1, f"transition_constraint_{base + 1}_{prev_time}_{n}")
            model.add_constraint(stop_prev2 + on_up_prev <= 1, f"transition_constraint_{base + 2}_{prev_time}_{n}")

    def _add_transition_constraints(
        self, model: OptimisationModel, time: DateTime, prev_time: DateTime
    ) -> None:
        n = self._eq.name
        off = self.off_var.get_value(time)
        off_prev = self.off_var.get_value(prev_time)
        on_up = self.on_up_var.get_value(time)
        on_up_prev = self.on_up_var.get_value(prev_time)
        on_down = self.on_down_var.get_value(time)
        on_down_prev = self.on_down_var.get_value(prev_time)

        if not self._has_flat and not self._has_start and not self._has_stop:
            return

        if self._has_flat:
            on_flat = self.on_flat_var.get_value(time)
            on_flat_prev = self.on_flat_var.get_value(prev_time)
            model.add_constraint(on_up_prev + on_down <= 1, f"transition_constraint_1_{time}_{n}")
            model.add_constraint(on_down_prev + on_up <= 1, f"transition_constraint_2_{time}_{n}")
            if self._has_stop and not self._has_start:
                stop = self.stop_var.get_value(time)
                stop_prev = self.stop_var.get_value(prev_time)
                model.add_constraint(on_up_prev + off <= 1, f"transition_constraint_3_{time}_{n}")
                model.add_constraint(on_down_prev + off <= 1, f"transition_constraint_4_{time}_{n}")
                model.add_constraint(stop_prev + on_flat <= 1, f"transition_constraint_5_{time}_{n}")
                model.add_constraint(stop_prev + on_down <= 1, f"transition_constraint_6_{time}_{n}")
                model.add_constraint(stop_prev + on_up <= 1, f"transition_constraint_7_{time}_{n}")
                model.add_constraint(on_up_prev + stop <= 1, f"transition_constraint_8_{time}_{n}")
                model.add_constraint(off_prev + stop <= 1, f"transition_constraint_9_{time}_{n}")
            elif self._has_start and not self._has_stop:
                start = self.on_start_var.get_value(time)
                start_prev = self.on_start_var.get_value(prev_time)
                model.add_constraint(on_up_prev + start <= 1, f"transition_constraint_3_{time}_{n}")
                model.add_constraint(on_down_prev + start <= 1, f"transition_constraint_4_{time}_{n}")
                model.add_constraint(on_flat_prev + start <= 1, f"transition_constraint_5_{time}_{n}")
                model.add_constraint(off + start_prev <= 1, f"transition_constraint_6_{time}_{n}")
                model.add_constraint(off_prev + on_flat <= 1, f"transition_constraint_7_{time}_{n}")
                model.add_constraint(off_prev + on_down <= 1, f"transition_constraint_8_{time}_{n}")
                model.add_constraint(off_prev + on_up <= 1, f"transition_constraint_9_{time}_{n}")
            elif self._has_stop and self._has_start:
                stop = self.stop_var.get_value(time)
                stop_prev = self.stop_var.get_value(prev_time)
                start = self.on_start_var.get_value(time)
                start_prev = self.on_start_var.get_value(prev_time)
                model.add_constraint(stop_prev + on_flat <= 1, f"transition_constraint_3_{time}_{n}")
                model.add_constraint(stop_prev + on_down <= 1, f"transition_constraint_4_{time}_{n}")
                model.add_constraint(stop_prev + on_up <= 1, f"transition_constraint_5_{time}_{n}")
                model.add_constraint(on_up_prev + stop <= 1, f"transition_constraint_6_{time}_{n}")
                model.add_constraint(off_prev + stop <= 1, f"transition_constraint_7_{time}_{n}")
                model.add_constraint(on_up_prev + start <= 1, f"transition_constraint_8_{time}_{n}")
                model.add_constraint(on_down_prev + start <= 1, f"transition_constraint_9_{time}_{n}")
                model.add_constraint(on_flat_prev + start <= 1, f"transition_constraint_10_{time}_{n}")
                model.add_constraint(on_up_prev + off <= 1, f"transition_constraint_11_{time}_{n}")
                model.add_constraint(on_down_prev + off <= 1, f"transition_constraint_12_{time}_{n}")
                model.add_constraint(on_flat_prev + off <= 1, f"transition_constraint_13_{time}_{n}")
                model.add_constraint(start_prev + off <= 1, f"transition_constraint_14_{time}_{n}")
                model.add_constraint(start_prev + stop <= 1, f"transition_constraint_15_{time}_{n}")
                model.add_constraint(stop_prev + start <= 1, f"transition_constraint_16_{time}_{n}")
                model.add_constraint(off_prev + on_up <= 1, f"transition_constraint_17_{time}_{n}")
                model.add_constraint(off_prev + on_flat <= 1, f"transition_constraint_18_{time}_{n}")
                model.add_constraint(off_prev + on_down <= 1, f"transition_constraint_19_{time}_{n}")
        else:
            if self._has_stop:
                stop = self.stop_var.get_value(time)
                stop_prev = self.stop_var.get_value(prev_time)
                model.add_constraint(stop_prev + on_up <= 1, f"transition_constraint_1_{time}_{n}")
                model.add_constraint(stop_prev + on_down <= 1, f"transition_constraint_2_{time}_{n}")
                model.add_constraint(off_prev + stop <= 1, f"transition_constraint_3_{time}_{n}")
                model.add_constraint(on_up_prev + off <= 1, f"transition_constraint_4_{time}_{n}")
                model.add_constraint(on_down_prev + off <= 1, f"transition_constraint_5_{time}_{n}")
            if self._has_start:
                start = self.on_start_var.get_value(time)
                start_prev = self.on_start_var.get_value(prev_time)
                if self._has_stop:
                    stop = self.stop_var.get_value(time)
                    model.add_constraint(on_up_prev + start <= 1, f"transition_constraint_6_{time}_{n}")
                    model.add_constraint(on_down_prev + start <= 1, f"transition_constraint_7_{time}_{n}")
                    model.add_constraint(start_prev + off <= 1, f"transition_constraint_8_{time}_{n}")
                    model.add_constraint(start_prev + stop <= 1, f"transition_constraint_9_{time}_{n}")
                    model.add_constraint(stop_prev + start <= 1, f"transition_constraint_10_{time}_{n}")
                    model.add_constraint(off_prev + on_up <= 1, f"transition_constraint_11_{time}_{n}")
                    model.add_constraint(off_prev + on_down <= 1, f"transition_constraint_12_{time}_{n}")
                else:
                    model.add_constraint(on_up_prev + start <= 1, f"transition_constraint_1_{time}_{n}")
                    model.add_constraint(on_down_prev + start <= 1, f"transition_constraint_2_{time}_{n}")
                    model.add_constraint(start_prev + off <= 1, f"transition_constraint_3_{time}_{n}")
                    model.add_constraint(off_prev + on_up <= 1, f"transition_constraint_4_{time}_{n}")
                    model.add_constraint(off_prev + on_down <= 1, f"transition_constraint_5_{time}_{n}")

    def _add_eviction_constraints(
        self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters
    ) -> None:
        n = self._eq.name
        ts = parameters.temporal.timestep  # type: ignore[attr-defined]
        if self._has_stop:
            stop = self.stop_var.get_value(time)
            evict_stop = time - (self._T_stop - 1) * ts
            toff_evict = self.turned_off.get_value(evict_stop)
            label = "stop_eviction_constraint" if self._has_start else "eviction_constraint"
            model.add_constraint(toff_evict + stop <= 1, f"{label}_{time}_{n}")
        if self._has_start:
            start = self.on_start_var.get_value(time)
            evict_start = time - (self._T_start - 1) * ts
            ton_evict = self.turned_on.get_value(evict_start)
            label = "start_eviction_constraint" if self._has_stop else "eviction_constraint"
            model.add_constraint(ton_evict + start <= 1, f"{label}_{time}_{n}")

    def _add_minimum_time_constraints(
        self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters
    ) -> None:
        n = self._eq.name
        ts = parameters.temporal.timestep  # type: ignore[attr-defined]
        start_date = parameters.temporal.start_date  # type: ignore[attr-defined]
        has_start_offset = self._T_start if self._has_start else 0
        has_stop_offset = self._T_stop if self._has_stop else 0

        on_expr = self.on_up_var.get_value(time) + self.on_down_var.get_value(time)
        if self._has_flat:
            on_expr = on_expr + self.on_flat_var.get_value(time)

        if self._T_on >= 2:
            for s in range(1, self._T_on):
                local_time = time - (s + has_start_offset) * ts
                model.add_constraint(
                    self.turned_on.get_value(local_time) <= on_expr,
                    f"minimum_time_on_{n}_{local_time}_{time}",
                )
            if self._has_flat and (self._has_stop or self._has_start) and time == start_date:
                prev_time = time - ts
                on_expr_prev = (
                    self.on_up_var.get_value(prev_time)
                    + self.on_down_var.get_value(prev_time)
                    + self.on_flat_var.get_value(prev_time)
                )
                for s in range(1, self._T_on):
                    local_time = time - (s + has_start_offset + 1) * ts
                    model.add_constraint(
                        self.turned_on.get_value(local_time) <= on_expr_prev,
                        f"minimum_time_on_{n}_{local_time}_{prev_time}",
                    )

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                local_time = time - (s + has_stop_offset) * ts
                model.add_constraint(
                    self.turned_off.get_value(local_time) <= self.off_var.get_value(time),
                    f"minimum_time_off_{n}_{local_time}_{time}",
                )

        if self._has_flat and self._T_stable >= 2:
            on_flat = self.on_flat_var.get_value(time)
            for s in range(1, self._T_stable - 1):
                local_time = time - s * ts
                model.add_constraint(
                    self.stable_var.get_value(local_time) <= on_flat,
                    f"minimum_time_stable_{n}_{local_time}_{time}",
                )
            if (self._has_stop or self._has_start) and time == start_date:
                prev_time = time - ts
                on_flat_prev = self.on_flat_var.get_value(prev_time)
                stable_name_time = time if (self._has_start and not self._has_stop) else prev_time
                for s in range(1, self._T_stable - 1):
                    local_time = time - (s + 1) * ts
                    model.add_constraint(
                        self.stable_var.get_value(local_time) <= on_flat_prev,
                        f"minimum_time_stable_{n}_{local_time}_{stable_name_time}",
                    )

        if self._has_stop and self._T_stop >= 2:
            stop = self.stop_var.get_value(time)
            for s in range(1, self._T_stop - 1):
                local_time = time - s * ts
                model.add_constraint(
                    self.turned_off.get_value(local_time) <= stop,
                    f"shutdown_ramp_{n}_{local_time}_{time}",
                )

        if self._has_start and self._T_start >= 2:
            start = self.on_start_var.get_value(time)
            prefix = "startup_ramp" if not self._has_flat else "start_up_ramp"
            for s in range(1, self._T_start - 1):
                local_time = time - s * ts
                model.add_constraint(
                    self.turned_on.get_value(local_time) <= start,
                    f"{prefix}_{n}_{local_time}_{time}",
                )

    def _add_power_bounds(self, model: OptimisationModel, time: DateTime) -> None:
        n = self._eq.name
        p = self.power_level_var.get_value(time)
        max_p = self._eq.maximum_power.get_value(time)
        min_p = self._eq.minimum_power.get_value(time)
        q_min = self._eq.minimum_power.max()
        on_up = self.on_up_var.get_value(time)
        on_down = self.on_down_var.get_value(time)
        on_sum = on_up + on_down
        if self._has_flat:
            on_sum = on_sum + self.on_flat_var.get_value(time)

        lb = min_p * on_sum
        ub = max_p * on_sum

        if self._has_stop:
            q_step_down = q_min / self._T_stop
            toff = self.turned_off.get_value(time)
            stop = self.stop_var.get_value(time)
            lb = lb + toff * (q_min - q_step_down)
            ub = ub + stop * q_min - toff * q_step_down

        if self._has_start:
            start = self.on_start_var.get_value(time)
            ub = ub + start * q_min

        model.add_constraint(p >= lb, f"lower_bound_{n}_{time}")
        model.add_constraint(p <= ub, f"upper_bound_{n}_{time}")

    def _add_dd_constraints(
        self, model: OptimisationModel, time: DateTime, prev_time: DateTime
    ) -> None:
        n = self._eq.name
        max_p = self._eq.maximum_power.get_value(time)
        min_p = -max_p
        stop = self.stop_var.get_value(time)
        dd_prev = self.dd_grad_var.get_value(prev_time)
        d_prev = self.down_grad_var.get_value(prev_time)
        model.add_constraint(dd_prev <= max_p * stop, f"DD_evol_1_{time}_{n}")
        model.add_constraint(dd_prev >= min_p * stop, f"DD_evol_2_{time}_{n}")
        model.add_constraint(dd_prev <= d_prev - min_p * (1 - stop), f"DD_evol_3_{time}_{n}")
        model.add_constraint(dd_prev >= d_prev - max_p * (1 - stop), f"DD_evol_4_{time}_{n}")

    def _add_gradient_constraints(
        self, model: OptimisationModel, time: DateTime, prev_time: DateTime
    ) -> None:
        n = self._eq.name
        delta_q = self._Delta_Q
        delta_q_unc = self._Delta_Q_unconstrained
        dq = delta_q if delta_q > 0 else delta_q_unc

        p = self.power_level_var.get_value(time)
        p_prev = self.power_level_var.get_value(prev_time)
        diff = p - p_prev

        ton = self.turned_on.get_value(time)
        toff = self.turned_off.get_value(time)

        if self._has_flat:
            entered_up_prev = self.entered_up_var.get_value(prev_time)
            entered_down_prev = self.entered_down_var.get_value(prev_time)
            u_prev = self.up_grad_var.get_value(prev_time)
            d_prev = self.down_grad_var.get_value(prev_time)
            up_base = dq * entered_up_prev + u_prev + d_prev
            down_base = -dq * entered_down_prev + u_prev + d_prev
        else:
            on_up_prev = self.on_up_var.get_value(prev_time)
            on_down_prev = self.on_down_var.get_value(prev_time)
            up_base = dq * on_up_prev
            down_base = -dq * on_down_prev

        q_min = self._eq.minimum_power.max()

        if self._has_start:
            q_step_up = q_min / self._T_start
            start_prev = self.on_start_var.get_value(prev_time)
            startup_contrib = q_step_up * ton + start_prev * q_step_up
            up_base = up_base + startup_contrib
            down_base = down_base + startup_contrib
        else:
            up_base = up_base + delta_q_unc * ton

        if self._has_stop:
            q_step_down = q_min / self._T_stop
            stop_prev = self.stop_var.get_value(prev_time)
            shutdown_contrib = -toff * q_step_down - stop_prev * q_step_down
            up_base = up_base + shutdown_contrib
            down_base = down_base + shutdown_contrib
            if self._has_flat:
                fds = self.flat_down_stop.get_value(time)
                dd_prev = self.dd_grad_var.get_value(prev_time)
                down_base = down_base + fds * dq - dd_prev
                up_base = up_base - dd_prev
            else:
                down_to_stop = self.down_to_stop_grad.get_value(time)
                down_base = down_base + down_to_stop * dq
        else:
            down_base = down_base - delta_q_unc * toff

        prefix = "upward_gradient" if delta_q > 0 else "unconstrained_upward_gradient"
        suffix = "downward_gradient" if delta_q > 0 else "unconstrained_downward_gradient"

        if not self._has_stop and not self._has_start and not self._has_flat:
            grad_time = prev_time
        elif self._has_start and not self._has_stop and not self._has_flat and delta_q == 0:
            grad_time = prev_time
        else:
            grad_time = time

        model.add_constraint(diff <= up_base, f"{prefix}_{n}_{grad_time}")
        model.add_constraint(diff >= down_base, f"{suffix}_{n}_{grad_time}")
