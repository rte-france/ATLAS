"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

from atlas.core.math.timeseries import Timeseries
from atlas.core.solver.solver_interface import OptimisationModel
from atlas.modules.portfolio_optimisation.steps.thermal.initial_conditions import ThermalInitialConditions
from atlas.modules.portfolio_optimisation.steps.thermal.initial_conditions_utils import (
    initialize_day_zero_core,
    initialize_day_zero_gradient_vars,
    initialize_day_zero_on_states,
    initialize_day_zero_stable_vars,
    initialize_flat_down_stop_initial_conditions,
    initialize_gradient_initial_conditions,
)
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class ThermalConstraintBuilder:
    """
    Unified constraint builder for ThermalPO — replaces combination_1..8.py.

    Combination encoding (T_stop>=1, T_start>=1, T_stable>=1):
        1:(0,0,0)  2:(1,0,0)  3:(0,0,1)  4:(0,1,0)
        5:(1,0,1)  6:(0,1,1)  7:(1,1,0)  8:(1,1,1)
    """

    def __init__(self, obj: ThermalPO) -> None:
        self._obj = obj
        self._has_stop = obj._T_stop >= 1
        self._has_start = obj._T_start >= 1
        self._has_flat = obj._T_stable >= 1

    # ──────────────────────────────────────────────────────────────────────
    # Initial conditions
    # ──────────────────────────────────────────────────────────────────────

    def build_initial_conditions(
        self,
        parameters: PortfolioOptimisationParameters,
    ) -> ThermalInitialConditions:
        obj = self._obj
        T_traceback = max(obj._T_on + obj._T_start, obj._T_off + obj._T_stop)

        initial_times: list[DateTime] = []
        stable_initial_times: list[DateTime] = []
        if T_traceback > 0:
            for k in range(T_traceback, 0, -1):
                initial_times.append(parameters.temporal.start_date - k * parameters.temporal.timestep)
        else:
            initial_times.append(parameters.temporal.start_date - parameters.temporal.timestep)
        for k in range(T_traceback, 1, -1):
            stable_initial_times.append(parameters.temporal.start_date - k * parameters.temporal.timestep)

        power_ts = (
            obj.power.get_forecast(parameters.temporal.execution_date, initial_times[0], initial_times[-1])
            if obj.power is not None
            else None
        )

        day_zero = power_ts is None
        if power_ts is not None:
            if parameters.temporal.start_date - parameters.temporal.timestep != power_ts.last_date():
                day_zero = True

        return ThermalInitialConditions(
            initial_times=initial_times,
            stable_initial_times=stable_initial_times,
            power_ts=power_ts,
            day_zero=day_zero,
        )

    def add_initial_conditions(self, parameters: PortfolioOptimisationParameters) -> None:
        ic = self.build_initial_conditions(parameters)
        if ic.day_zero:
            self._init_day_zero(parameters, ic)
        else:
            self._init_from_previous(parameters, ic)

    def _init_day_zero(
        self,
        parameters: PortfolioOptimisationParameters,
        ic: ThermalInitialConditions,
    ) -> None:
        obj = self._obj
        for time in ic.initial_times:
            initialize_day_zero_core(obj, time)
            if not self._has_flat:
                initialize_day_zero_on_states(obj, time)
            else:
                initialize_day_zero_gradient_vars(obj, time)
            if self._has_stop:
                obj.stop_var.set_extended(time, 0)
                if not self._has_flat:
                    obj.down_to_stop_grad.set_extended(time, 0)
                else:
                    obj.flat_down_stop.set_extended(time, 0)
            if self._has_start:
                obj.on_start_var.set_extended(time, 0)

        for time in ic.stable_initial_times:
            initialize_day_zero_stable_vars(obj, time)

        # Comb 3 only: init gradients if power_ts exists even in day_zero
        if self._has_flat and not self._has_stop and not self._has_start:
            if isinstance(ic.power_ts, Timeseries):
                initialize_gradient_initial_conditions(obj, parameters)

    def _init_from_previous(
        self,
        parameters: PortfolioOptimisationParameters,
        ic: ThermalInitialConditions,
    ) -> None:
        obj = self._obj
        if not isinstance(ic.power_ts, Timeseries):
            raise ValueError("power_ts is required when day_zero is False")
        if obj.minimum_power is None:
            raise ValueError("minimum_power is required when day_zero is False")

        for time in ic.initial_times:
            self._init_one_time(obj, parameters, ic.extended_start_date, time, ic.power_ts)

        if self._has_flat:
            self._init_stable_times(obj, parameters, ic)
            initialize_gradient_initial_conditions(obj, parameters)
            if self._has_stop:
                self._init_flat_down_stop(obj, parameters, ic)

    def _init_one_time(
        self,
        obj: ThermalPO,
        parameters: PortfolioOptimisationParameters,
        extended_start_date: DateTime,
        time: DateTime,
        power_ts: Timeseries,
    ) -> None:
        ts = parameters.temporal.timestep
        if time in power_ts:
            power_t = power_ts.get_value(time)
            obj.power_level_var.set_extended(time, power_t)

            if self._has_start or self._has_stop:
                assert obj.minimum_power is not None
                min_power = obj.minimum_power.get_value(time)
                if power_t >= min_power:
                    obj.off_var.set_extended(time, 0)
                    if self._has_stop:
                        obj.stop_var.set_extended(time, 0)
                    if self._has_start:
                        obj.on_start_var.set_extended(time, 0)
                    if not self._has_flat:
                        obj.on_up_var.set_extended(time, 1)
                        obj.on_down_var.set_extended(time, 1)
                elif power_t > 0:
                    obj.off_var.set_extended(time, 0)
                    if self._has_stop:
                        obj.stop_var.set_extended(time, 1)
                    if self._has_start:
                        obj.on_start_var.set_extended(time, 1)
                    if not self._has_flat:
                        obj.on_up_var.set_extended(time, 0)
                        obj.on_down_var.set_extended(time, 0)
                else:
                    obj.off_var.set_extended(time, 1)
                    if self._has_stop:
                        obj.stop_var.set_extended(time, 0)
                    if self._has_start:
                        obj.on_start_var.set_extended(time, 0)
                    if not self._has_flat:
                        obj.on_up_var.set_extended(time, 0)
                        obj.on_down_var.set_extended(time, 0)
            else:
                # Combs 1 and 3: no ramp states
                if power_t > 0:
                    obj.off_var.set_extended(time, 0)
                    if not self._has_flat:
                        obj.on_up_var.set_extended(time, 1)
                        obj.on_down_var.set_extended(time, 0)
                else:
                    obj.power_level_var.set_extended(time, 0)
                    obj.off_var.set_extended(time, 1)
                    if not self._has_flat:
                        obj.on_up_var.set_extended(time, 0)
                        obj.on_down_var.set_extended(time, 0)
        else:
            obj.power_level_var.set_extended(time, 0)
            obj.off_var.set_extended(time, 1)
            if self._has_stop:
                obj.stop_var.set_extended(time, 0)
            if self._has_start:
                obj.on_start_var.set_extended(time, 0)
            if not self._has_flat:
                obj.on_up_var.set_extended(time, 0)
                obj.on_down_var.set_extended(time, 0)

        obj.turned_on.set_extended(time, 0)
        obj.turned_off.set_extended(time, 0)
        if self._has_stop and not self._has_flat:
            obj.down_to_stop_grad.set_extended(time, 0)

        if time == extended_start_date:
            return

        prev_time = time - ts

        # Resolve start/stop ambiguity for combs 7 and 8
        if self._has_start and self._has_stop and time in power_ts:
            power_t = power_ts.get_value(time)
            prev_power = power_ts.get_value(prev_time) if prev_time in power_ts else 0
            if obj.on_start_var.get_extended_value(time) == 1:
                if power_t > prev_power:
                    obj.stop_var.set_extended(time, 0)
                elif power_t < prev_power:
                    obj.stop_var.set_extended(time, 1)
                    obj.on_start_var.set_extended(time, 0)

        # turned_off
        if self._has_stop:
            if obj.stop_var.get_extended_value(time) - obj.stop_var.get_extended_value(prev_time) == 1:
                obj.turned_off.set_extended(time, 1)
        else:
            if obj.off_var.get_extended_value(time) - obj.off_var.get_extended_value(prev_time) == 1:
                obj.turned_off.set_extended(time, 1)

        # turned_on
        if self._has_start:
            if obj.on_start_var.get_extended_value(time) - obj.on_start_var.get_extended_value(prev_time) == 1:
                obj.turned_on.set_extended(time, 1)
        else:
            if obj.off_var.get_extended_value(time) - obj.off_var.get_extended_value(prev_time) == -1:
                obj.turned_on.set_extended(time, 1)

        # down_to_stop_grad (combs 2 and 7: has_stop and not has_flat)
        if self._has_stop and not self._has_flat:
            if obj.stop_var.get_extended_value(time) - obj.on_down_var.get_extended_value(prev_time) == 0:
                obj.down_to_stop_grad.set_extended(time, 1)

    def _init_stable_times(
        self,
        obj: ThermalPO,
        parameters: PortfolioOptimisationParameters,
        ic: ThermalInitialConditions,
    ) -> None:
        ts = parameters.temporal.timestep
        for time in ic.stable_initial_times:
            next_time = time + ts
            current_power = obj.power_level_var.get_extended_value(time)
            next_power = obj.power_level_var.get_extended_value(next_time)

            obj.stable_var.set_extended(time, 0)
            obj.entered_up_var.set_extended(time, 0)
            obj.entered_down_var.set_extended(time, 0)

            if obj.off_var.get_extended_value(time) == 0:
                in_ramp = (self._has_stop and obj.stop_var.get_extended_value(time) == 1) or (
                    self._has_start and obj.on_start_var.get_extended_value(time) == 1
                )
                if in_ramp:
                    obj.on_up_var.set_extended(time, 0)
                    obj.on_down_var.set_extended(time, 0)
                    obj.on_flat_var.set_extended(time, 0)
                else:
                    if current_power < next_power:
                        obj.on_up_var.set_extended(time, 1)
                        obj.on_down_var.set_extended(time, 0)
                        obj.on_flat_var.set_extended(time, 0)
                    elif current_power > next_power:
                        obj.on_up_var.set_extended(time, 0)
                        obj.on_down_var.set_extended(time, 1)
                        obj.on_flat_var.set_extended(time, 0)
                    else:
                        obj.on_up_var.set_extended(time, 0)
                        obj.on_down_var.set_extended(time, 0)
                        obj.on_flat_var.set_extended(time, 1)
            else:
                obj.on_up_var.set_extended(time, 0)
                obj.on_down_var.set_extended(time, 0)
                obj.on_flat_var.set_extended(time, 0)

            if time != ic.extended_start_date and obj.off_var.get_extended_value(time) != 1:
                prev_time = time - ts
                if obj.on_flat_var.get_extended_value(time) - obj.on_flat_var.get_extended_value(prev_time) == 1:
                    obj.stable_var.set_extended(time, 1)
                if obj.on_up_var.get_extended_value(time) - obj.on_up_var.get_extended_value(prev_time) == 1:
                    obj.entered_up_var.set_extended(time, 1)
                if obj.on_down_var.get_extended_value(time) - obj.on_down_var.get_extended_value(prev_time) == 1:
                    obj.entered_down_var.set_extended(time, 1)

    def _init_flat_down_stop(
        self,
        obj: ThermalPO,
        parameters: PortfolioOptimisationParameters,
        ic: ThermalInitialConditions,
    ) -> None:
        ts = parameters.temporal.timestep
        for idx, time in enumerate(ic.stable_initial_times):
            if idx >= 2:
                initialize_flat_down_stop_initial_conditions(obj, time, time - ts, time - 2 * ts)
        initialize_flat_down_stop_initial_conditions(
            obj,
            parameters.temporal.start_date - ts,
            parameters.temporal.start_date - 2 * ts,
            parameters.temporal.start_date - 3 * ts,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Constraints (called once per timestep)
    # ──────────────────────────────────────────────────────────────────────

    def add_constraints(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ) -> None:
        obj = self._obj
        ts = parameters.temporal.timestep
        prev_time = time - ts

        self._add_turned_on(model, obj, time, prev_time)
        self._add_turned_off(model, obj, time, prev_time)

        if self._has_flat:
            self._add_stable(model, obj, time, prev_time)
            if self._has_stop:
                self._add_flat_down_stop(model, obj, time, prev_time, ts)
            self._add_entered_up_down(model, obj, time, prev_time)
            self._add_gradient_auxiliaries(model, obj, time, prev_time, parameters)

        if self._has_stop and not self._has_flat:
            self._add_down_to_stop_evol(model, obj, time, prev_time)

        self._add_mutual_exclusion(model, obj, time)

        if self._has_flat and time == parameters.temporal.start_date:
            self._add_initial_boundary_constraints(model, obj, time, prev_time, ts)

        self._add_transition_constraints(model, obj, time, prev_time)
        self._add_eviction_constraints(model, obj, time, parameters)
        self._add_minimum_time_constraints(model, obj, time, parameters)
        self._add_fill_up_constraints(model, obj, time, parameters)
        self._add_reserve_constraints(model, obj, time, parameters)
        self._add_power_bounds(model, obj, time)

        if time in obj.optimisation_time_window[:-2]:
            if self._has_flat and self._has_stop:
                self._add_dd_constraints(model, obj, time, prev_time, parameters)
            self._add_gradient_constraints(model, obj, time, prev_time)

    # ── turned_on / turned_off ────────────────────────────────────────────

    def _add_turned_on(self, model, obj, time, prev_time):
        ton = obj.turned_on.get_value(time)
        off = obj.off_var.get_value(time)
        off_prev = obj.off_var.get_value(prev_time)
        n = obj.name
        model.add_constraint(ton <= 1 - off, f"t_on_evol_1_{time}_{n}")
        model.add_constraint(ton <= off_prev, f"t_on_evol_2_{time}_{n}")
        model.add_constraint(ton >= off_prev - off, f"t_on_evol_3_{time}_{n}")

    def _add_turned_off(self, model, obj, time, prev_time):
        toff = obj.turned_off.get_value(time)
        n = obj.name
        if self._has_stop:
            stop = obj.stop_var.get_value(time)
            stop_prev = obj.stop_var.get_value(prev_time)
            model.add_constraint(toff <= 1 - stop_prev, f"t_off_evol_1_{time}_{n}")
            model.add_constraint(toff <= stop, f"t_off_evol_2_{time}_{n}")
            model.add_constraint(toff >= stop - stop_prev, f"t_off_evol_3_{time}_{n}")
        else:
            off = obj.off_var.get_value(time)
            off_prev = obj.off_var.get_value(prev_time)
            model.add_constraint(toff <= 1 - off_prev, f"t_off_evol_1_{time}_{n}")
            model.add_constraint(toff <= off, f"t_off_evol_2_{time}_{n}")
            model.add_constraint(toff >= off - off_prev, f"t_off_evol_3_{time}_{n}")

    # ── stable / flat_down_stop / entered_up_down ─────────────────────────

    def _add_stable(self, model, obj, time, prev_time):
        stab = obj.stable_var.get_value(time)
        flat = obj.on_flat_var.get_value(time)
        flat_prev = obj.on_flat_var.get_value(prev_time)
        n = obj.name
        model.add_constraint(stab <= 1 - flat_prev, f"stable_evol_1_{time}_{n}")
        model.add_constraint(stab <= flat, f"stable_evol_2_{time}_{n}")
        model.add_constraint(stab >= flat - flat_prev, f"stable_evol_3_{time}_{n}")

    def _add_flat_down_stop(self, model, obj, time, prev_time, ts):
        fds = obj.flat_down_stop.get_value(time)
        stop = obj.stop_var.get_value(time)
        on_down_prev = obj.on_down_var.get_value(prev_time)
        flat_prev2 = obj.on_flat_var.get_value(prev_time - ts)
        n = obj.name
        # comb 5 (no start): "flat_down_stop_evol_*"; comb 8 (has_start): "flat_down_stop_*"
        prefix = "flat_down_stop_evol" if not self._has_start else "flat_down_stop"
        model.add_constraint(fds <= stop, f"{prefix}_1_{time}_{n}")
        model.add_constraint(fds <= on_down_prev, f"{prefix}_2_{time}_{n}")
        model.add_constraint(fds <= flat_prev2, f"{prefix}_3_{time}_{n}")
        model.add_constraint(fds >= stop + on_down_prev + flat_prev2 - 2, f"{prefix}_4_{time}_{n}")

    def _add_entered_up_down(self, model, obj, time, prev_time):
        eu = obj.entered_up_var.get_value(time)
        on_up = obj.on_up_var.get_value(time)
        on_up_prev = obj.on_up_var.get_value(prev_time)
        ed = obj.entered_down_var.get_value(time)
        on_down = obj.on_down_var.get_value(time)
        on_down_prev = obj.on_down_var.get_value(prev_time)
        n = obj.name
        model.add_constraint(eu <= 1 - on_up_prev, f"entered_up_evol_1_{time}_{n}")
        model.add_constraint(eu <= on_up, f"entered_up_evol_2_{time}_{n}")
        model.add_constraint(eu >= on_up - on_up_prev, f"entered_up_evol_3_{time}_{n}")
        model.add_constraint(ed <= 1 - on_down_prev, f"entered_down_evol_1_{time}_{n}")
        model.add_constraint(ed <= on_down, f"entered_down_evol_2_{time}_{n}")
        model.add_constraint(ed >= on_down - on_down_prev, f"entered_down_evol_3_{time}_{n}")

    # ── gradient auxiliaries (tilde_U, tilde_D, U, D) ────────────────────

    def _add_gradient_auxiliaries(self, model, obj, time, prev_time, parameters):
        n = obj.name
        max_p = obj.maximum_power.get_value(time)
        min_p = -max_p
        power = obj.power_level_var.get_value(time)
        power_prev = obj.power_level_var.get_value(prev_time)
        dq = power - power_prev

        on_up_prev = obj.on_up_var.get_value(prev_time)
        on_down_prev = obj.on_down_var.get_value(prev_time)
        on_up = obj.on_up_var.get_value(time)
        on_down = obj.on_down_var.get_value(time)
        aux_u = obj.aux_up_grad_var.get_value(time)
        aux_d = obj.aux_down_grad_var.get_value(time)
        u = obj.up_grad_var.get_value(time)
        d = obj.down_grad_var.get_value(time)

        # tilde_U
        model.add_constraint(aux_u <= max_p * on_up_prev, f"tilde_U_evol_1_{time}_{n}")
        model.add_constraint(aux_u >= min_p * on_up_prev, f"tilde_U_evol_2_{time}_{n}")
        model.add_constraint(aux_u <= dq - min_p * (1 - on_up_prev), f"tilde_U_evol_3_{time}_{n}")
        model.add_constraint(aux_u >= dq - max_p * (1 - on_up_prev), f"tilde_U_evol_4_{time}_{n}")
        # tilde_D
        model.add_constraint(aux_d <= max_p * on_down_prev, f"tilde_D_evol_1_{time}_{n}")
        model.add_constraint(aux_d >= min_p * on_down_prev, f"tilde_D_evol_2_{time}_{n}")
        model.add_constraint(aux_d <= dq - min_p * (1 - on_down_prev), f"tilde_D_evol_3_{time}_{n}")
        model.add_constraint(aux_d >= dq - max_p * (1 - on_down_prev), f"tilde_D_evol_4_{time}_{n}")
        # U
        model.add_constraint(u <= max_p * on_up, f"U_evol_1_{time}_{n}")
        model.add_constraint(u >= min_p * on_up, f"U_evol_2_{time}_{n}")
        model.add_constraint(u <= aux_u - min_p * (1 - on_up), f"U_evol_3_{time}_{n}")
        model.add_constraint(u >= aux_u - max_p * (1 - on_up), f"U_evol_4_{time}_{n}")
        # D
        model.add_constraint(d <= max_p * on_down, f"D_evol_1_{time}_{n}")
        model.add_constraint(d >= min_p * on_down, f"D_evol_2_{time}_{n}")
        model.add_constraint(d <= aux_d - min_p * (1 - on_down), f"D_evol_3_{time}_{n}")
        model.add_constraint(d >= aux_d - max_p * (1 - on_down), f"D_evol_4_{time}_{n}")

    # ── down_to_stop_grad evolution (combs 2 and 7: has_stop and not has_flat) ──

    def _add_down_to_stop_evol(self, model, obj, time, prev_time):
        n = obj.name
        dts = obj.down_to_stop_grad.get_value(time)
        on_down = obj.on_down_var.get_value(time)
        on_down_prev = obj.on_down_var.get_value(prev_time)
        if self._has_start:
            # comb 7: down_to_stop tracks transition from on_down → stop
            stop = obj.stop_var.get_value(time)
            model.add_constraint(dts <= stop, f"down_to_stop_evol_1_{time}_{n}")
            model.add_constraint(dts <= on_down_prev, f"down_to_stop_evol_2_{time}_{n}")
            model.add_constraint(dts >= stop + on_down_prev - 1, f"down_to_stop_evol_3_{time}_{n}")
        else:
            # comb 2: down_to_stop tracks on_down entry after on_down_prev
            model.add_constraint(dts <= 1 - on_down_prev, f"t_stop_evol_1_{time}_{n}")
            model.add_constraint(dts <= on_down, f"t_stop_evol_2_{time}_{n}")
            model.add_constraint(dts >= on_down - on_down_prev, f"t_stop_evol_3_{time}_{n}")

    # ── mutual exclusion ──────────────────────────────────────────────────

    def _add_mutual_exclusion(self, model, obj, time):
        n = obj.name
        expr = obj.off_var.get_value(time) + obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time)
        if self._has_flat:
            expr = expr + obj.on_flat_var.get_value(time)
        if self._has_stop:
            expr = expr + obj.stop_var.get_value(time)
        if self._has_start:
            expr = expr + obj.on_start_var.get_value(time)
        model.add_constraint(expr == 1, f"mutual_exclusion_{time}_{n}")

    # ── initial boundary constraints (time == start_date, has_flat) ───────

    def _add_initial_boundary_constraints(self, model, obj, time, prev_time, ts):
        """Add constraints for prev_time that must exist when has_flat (start_date boundary)."""
        n = obj.name
        prev2 = prev_time - ts

        on_flat_prev = obj.on_flat_var.get_value(prev_time)
        on_flat_prev2 = obj.on_flat_var.get_value(prev2)
        on_up_prev = obj.on_up_var.get_value(prev_time)
        on_up_prev2 = obj.on_up_var.get_value(prev2)
        on_down_prev = obj.on_down_var.get_value(prev_time)
        on_down_prev2 = obj.on_down_var.get_value(prev2)
        stable_prev = obj.stable_var.get_value(prev_time)
        entered_up_prev = obj.entered_up_var.get_value(prev_time)
        entered_down_prev = obj.entered_down_var.get_value(prev_time)

        # stable constraints at prev_time
        # comb 8 (has_stop and has_start and has_flat) has a different first constraint
        if self._has_stop and self._has_start:
            model.add_constraint(stable_prev <= on_flat_prev2, f"stable_evol_1_{prev_time}_{n}")
        else:
            model.add_constraint(stable_prev <= 1 - on_flat_prev2, f"stable_evol_1_{prev_time}_{n}")
        model.add_constraint(stable_prev <= on_flat_prev, f"stable_evol_2_{prev_time}_{n}")
        model.add_constraint(stable_prev >= on_flat_prev - on_flat_prev2, f"stable_evol_3_{prev_time}_{n}")

        # entered_up / entered_down at prev_time
        model.add_constraint(entered_up_prev <= 1 - on_up_prev2, f"entered_up_evol_1_{prev_time}_{n}")
        model.add_constraint(entered_up_prev <= on_up_prev, f"entered_up_evol_2_{prev_time}_{n}")
        model.add_constraint(entered_up_prev >= on_up_prev - on_up_prev2, f"entered_up_evol_3_{prev_time}_{n}")
        model.add_constraint(entered_down_prev <= 1 - on_down_prev2, f"entered_down_evol_1_{prev_time}_{n}")
        model.add_constraint(entered_down_prev <= on_down_prev, f"entered_down_evol_2_{prev_time}_{n}")
        model.add_constraint(entered_down_prev >= on_down_prev - on_down_prev2, f"entered_down_evol_3_{prev_time}_{n}")

        # mutual exclusion at prev_time
        expr_prev = obj.off_var.get_value(prev_time) + on_up_prev + on_down_prev + on_flat_prev
        if self._has_stop:
            expr_prev = expr_prev + obj.stop_var.get_value(prev_time)
        if self._has_start:
            expr_prev = expr_prev + obj.on_start_var.get_value(prev_time)
        model.add_constraint(expr_prev == 1, f"mutual_exclusion_{prev_time}_{n}")

        # transition constraints at prev_time
        model.add_constraint(on_up_prev2 + on_down_prev <= 1, f"transition_constraint_1_{prev_time}_{n}")
        model.add_constraint(on_down_prev2 + on_up_prev <= 1, f"transition_constraint_2_{prev_time}_{n}")
        if self._has_stop:
            stop_prev2 = obj.stop_var.get_value(prev2)
            # comb 5 (no start): TC5/6/7; comb 8 (has_start): TC3/4/5
            base = 3 if self._has_start else 5
            model.add_constraint(stop_prev2 + on_flat_prev <= 1, f"transition_constraint_{base}_{prev_time}_{n}")
            model.add_constraint(stop_prev2 + on_down_prev <= 1, f"transition_constraint_{base + 1}_{prev_time}_{n}")
            model.add_constraint(stop_prev2 + on_up_prev <= 1, f"transition_constraint_{base + 2}_{prev_time}_{n}")

    # ── transition constraints ────────────────────────────────────────────

    def _add_transition_constraints(self, model, obj, time, prev_time):
        n = obj.name
        off = obj.off_var.get_value(time)
        off_prev = obj.off_var.get_value(prev_time)
        on_up = obj.on_up_var.get_value(time)
        on_up_prev = obj.on_up_var.get_value(prev_time)
        on_down = obj.on_down_var.get_value(time)
        on_down_prev = obj.on_down_var.get_value(prev_time)

        if not self._has_flat and not self._has_start and not self._has_stop:
            return  # comb 1: no forbidden transitions

        if self._has_flat:
            on_flat = obj.on_flat_var.get_value(time)
            on_flat_prev = obj.on_flat_var.get_value(prev_time)
            # TC1, TC2 present for all flat combinations
            model.add_constraint(on_up_prev + on_down <= 1, f"transition_constraint_1_{time}_{n}")
            model.add_constraint(on_down_prev + on_up <= 1, f"transition_constraint_2_{time}_{n}")
            if self._has_stop and not self._has_start:
                # comb 5: has_flat + has_stop only
                stop = obj.stop_var.get_value(time)
                stop_prev = obj.stop_var.get_value(prev_time)
                model.add_constraint(on_up_prev + off <= 1, f"transition_constraint_3_{time}_{n}")
                model.add_constraint(on_down_prev + off <= 1, f"transition_constraint_4_{time}_{n}")
                model.add_constraint(stop_prev + on_flat <= 1, f"transition_constraint_5_{time}_{n}")
                model.add_constraint(stop_prev + on_down <= 1, f"transition_constraint_6_{time}_{n}")
                model.add_constraint(stop_prev + on_up <= 1, f"transition_constraint_7_{time}_{n}")
                model.add_constraint(on_up_prev + stop <= 1, f"transition_constraint_8_{time}_{n}")
                model.add_constraint(off_prev + stop <= 1, f"transition_constraint_9_{time}_{n}")
            elif self._has_start and not self._has_stop:
                # comb 6: has_flat + has_start only
                start = obj.on_start_var.get_value(time)
                start_prev = obj.on_start_var.get_value(prev_time)
                model.add_constraint(on_up_prev + start <= 1, f"transition_constraint_3_{time}_{n}")
                model.add_constraint(on_down_prev + start <= 1, f"transition_constraint_4_{time}_{n}")
                model.add_constraint(on_flat_prev + start <= 1, f"transition_constraint_5_{time}_{n}")
                model.add_constraint(off + start_prev <= 1, f"transition_constraint_6_{time}_{n}")
                model.add_constraint(off_prev + on_flat <= 1, f"transition_constraint_7_{time}_{n}")
                model.add_constraint(off_prev + on_down <= 1, f"transition_constraint_8_{time}_{n}")
                model.add_constraint(off_prev + on_up <= 1, f"transition_constraint_9_{time}_{n}")
            elif self._has_stop and self._has_start:
                # comb 8: has_flat + has_stop + has_start
                stop = obj.stop_var.get_value(time)
                stop_prev = obj.stop_var.get_value(prev_time)
                start = obj.on_start_var.get_value(time)
                start_prev = obj.on_start_var.get_value(prev_time)
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
            # else: comb 3 (has_flat only): only TC1, TC2 above
        else:
            # No flat: combs 2, 4, 7
            if self._has_stop:
                stop = obj.stop_var.get_value(time)
                stop_prev = obj.stop_var.get_value(prev_time)
                model.add_constraint(stop_prev + on_up <= 1, f"transition_constraint_1_{time}_{n}")
                model.add_constraint(stop_prev + on_down <= 1, f"transition_constraint_2_{time}_{n}")
                model.add_constraint(off_prev + stop <= 1, f"transition_constraint_3_{time}_{n}")
                model.add_constraint(on_up_prev + off <= 1, f"transition_constraint_4_{time}_{n}")
                model.add_constraint(on_down_prev + off <= 1, f"transition_constraint_5_{time}_{n}")
            if self._has_start:
                start = obj.on_start_var.get_value(time)
                start_prev = obj.on_start_var.get_value(prev_time)
                if self._has_stop:
                    # comb 7: start constraints follow stop constraints (6-12)
                    stop = obj.stop_var.get_value(time)
                    model.add_constraint(on_up_prev + start <= 1, f"transition_constraint_6_{time}_{n}")
                    model.add_constraint(on_down_prev + start <= 1, f"transition_constraint_7_{time}_{n}")
                    model.add_constraint(start_prev + off <= 1, f"transition_constraint_8_{time}_{n}")
                    model.add_constraint(start_prev + stop <= 1, f"transition_constraint_9_{time}_{n}")
                    model.add_constraint(stop_prev + start <= 1, f"transition_constraint_10_{time}_{n}")
                    model.add_constraint(off_prev + on_up <= 1, f"transition_constraint_11_{time}_{n}")
                    model.add_constraint(off_prev + on_down <= 1, f"transition_constraint_12_{time}_{n}")
                else:
                    # comb 4: start constraints are the only ones (1-5)
                    model.add_constraint(on_up_prev + start <= 1, f"transition_constraint_1_{time}_{n}")
                    model.add_constraint(on_down_prev + start <= 1, f"transition_constraint_2_{time}_{n}")
                    model.add_constraint(start_prev + off <= 1, f"transition_constraint_3_{time}_{n}")
                    model.add_constraint(off_prev + on_up <= 1, f"transition_constraint_4_{time}_{n}")
                    model.add_constraint(off_prev + on_down <= 1, f"transition_constraint_5_{time}_{n}")

    # ── eviction constraints ──────────────────────────────────────────────

    def _add_eviction_constraints(self, model, obj, time, parameters):
        n = obj.name
        ts = parameters.temporal.timestep
        if self._has_stop:
            stop = obj.stop_var.get_value(time)
            evict_stop = time - (obj._T_stop - 1) * ts
            toff_evict = obj.turned_off.get_value(evict_stop)
            label = "stop_eviction_constraint" if self._has_start else "eviction_constraint"
            model.add_constraint(toff_evict + stop <= 1, f"{label}_{time}_{n}")
        if self._has_start:
            start = obj.on_start_var.get_value(time)
            evict_start = time - (obj._T_start - 1) * ts
            ton_evict = obj.turned_on.get_value(evict_start)
            label = "start_eviction_constraint" if self._has_stop else "eviction_constraint"
            model.add_constraint(ton_evict + start <= 1, f"{label}_{time}_{n}")

    # ── minimum time constraints ──────────────────────────────────────────

    def _add_minimum_time_constraints(self, model, obj, time, parameters):
        n = obj.name
        ts = parameters.temporal.timestep
        has_start_offset = obj._T_start if self._has_start else 0
        has_stop_offset = obj._T_stop if self._has_stop else 0

        on_expr = obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time)
        if self._has_flat:
            on_expr = on_expr + obj.on_flat_var.get_value(time)

        if obj._T_on >= 2:
            for s in range(1, obj._T_on):
                local_time = time - (s + has_start_offset) * ts
                model.add_constraint(
                    obj.turned_on.get_value(local_time) <= on_expr,
                    f"minimum_time_on_{n}_{local_time}_{time}",
                )
            if self._has_flat and (self._has_stop or self._has_start) and time == parameters.temporal.start_date:
                prev_time = time - ts
                on_expr_prev = (
                    obj.on_up_var.get_value(prev_time)
                    + obj.on_down_var.get_value(prev_time)
                    + obj.on_flat_var.get_value(prev_time)
                )
                for s in range(1, obj._T_on):
                    local_time = time - (s + has_start_offset + 1) * ts
                    model.add_constraint(
                        obj.turned_on.get_value(local_time) <= on_expr_prev,
                        f"minimum_time_on_{n}_{local_time}_{prev_time}",
                    )

        if obj._T_off >= 2:
            for s in range(1, obj._T_off):
                local_time = time - (s + has_stop_offset) * ts
                model.add_constraint(
                    obj.turned_off.get_value(local_time) <= obj.off_var.get_value(time),
                    f"minimum_time_off_{n}_{local_time}_{time}",
                )

        if self._has_flat and obj._T_stable >= 2:
            on_flat = obj.on_flat_var.get_value(time)
            for s in range(1, obj._T_stable - 1):
                local_time = time - s * ts
                model.add_constraint(
                    obj.stable_var.get_value(local_time) <= on_flat,
                    f"minimum_time_stable_{n}_{local_time}_{time}",
                )
            if (self._has_stop or self._has_start) and time == parameters.temporal.start_date:
                prev_time = time - ts
                on_flat_prev = obj.on_flat_var.get_value(prev_time)
                # comb 6 (has_start only + has_flat): uses current time in name, not prev_time
                stable_name_time = time if (self._has_start and not self._has_stop) else prev_time
                for s in range(1, obj._T_stable - 1):
                    local_time = time - (s + 1) * ts
                    model.add_constraint(
                        obj.stable_var.get_value(local_time) <= on_flat_prev,
                        f"minimum_time_stable_{n}_{local_time}_{stable_name_time}",
                    )

        if self._has_stop and obj._T_stop >= 2:
            stop = obj.stop_var.get_value(time)
            for s in range(1, obj._T_stop - 1):
                local_time = time - s * ts
                model.add_constraint(
                    obj.turned_off.get_value(local_time) <= stop,
                    f"shutdown_ramp_{n}_{local_time}_{time}",
                )

        if self._has_start and obj._T_start >= 2:
            start = obj.on_start_var.get_value(time)
            prefix = "startup_ramp" if not self._has_flat else "start_up_ramp"
            for s in range(1, obj._T_start - 1):
                local_time = time - s * ts
                model.add_constraint(
                    obj.turned_on.get_value(local_time) <= start,
                    f"{prefix}_{n}_{local_time}_{time}",
                )

    # ── fill-up / reserves / power bounds ────────────────────────────────

    def _add_fill_up_constraints(self, model, obj, time, parameters):
        n = obj.name
        eps = parameters.allowed_round_off_error
        p = obj.power_level_var.get_value(time)
        max_p = obj.maximum_power.get_value(time)
        min_p = obj.minimum_power.get_value(time)
        ru = model.get_variable(f"reserves_up_{n}_{time}")
        rd = model.get_variable(f"reserves_down_{n}_{time}")
        aru = model.get_variable(f"automated_reserves_up_{n}_{time}")
        ard = model.get_variable(f"automated_reserves_down_{n}_{time}")
        uru = model.get_variable(f"unprovided_reserves_up_{n}_{time}")
        urd = model.get_variable(f"unprovided_reserves_down_{n}_{time}")
        rr = model.get_variable(f"relaxed_reserves_{n}_{time}")

        model.add_constraint(p + ru + aru + uru <= max_p + eps, f"up_fillup_1_{time}_{n}")
        model.add_constraint(p + ru + aru + uru >= max_p - eps, f"up_fillup_2_{time}_{n}")
        model.add_constraint(p - rd - ard - urd + rr <= min_p + eps, f"down_fillup_1_{time}_{n}")
        model.add_constraint(p - rd - ard - urd + rr >= min_p - eps, f"down_fillup_2_{time}_{n}")

    def _add_reserve_constraints(self, model, obj, time, parameters):
        n = obj.name
        max_p = obj.maximum_power.get_value(time)
        min_p = obj.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(obj)
        off = obj.off_var.get_value(time)
        ru = model.get_variable(f"reserves_up_{n}_{time}")
        rd = model.get_variable(f"reserves_down_{n}_{time}")
        aru = model.get_variable(f"automated_reserves_up_{n}_{time}")
        ard = model.get_variable(f"automated_reserves_down_{n}_{time}")
        rr = model.get_variable(f"relaxed_reserves_{n}_{time}")

        on_sum = obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time)
        if self._has_flat:
            on_flat = obj.on_flat_var.get_value(time)
            on_sum_flat = on_sum + on_flat
        else:
            on_sum_flat = on_sum

        model.add_constraint(rr <= min_p * (1 - on_sum_flat), f"relaxed_reserves_{time}_{n}")

        # Automated reserves unavailable when OFF/START/STOP
        unavail = off
        if self._has_start:
            unavail = unavail + obj.on_start_var.get_value(time)
        if self._has_stop:
            unavail = unavail + obj.stop_var.get_value(time)
        model.add_constraint(aru <= maximum_automated * (1 - unavail), f"automated_reserves_up_max_{time}_{n}")
        model.add_constraint(ard <= maximum_automated * (1 - unavail), f"automated_reserves_down_max_{time}_{n}")

        # Equipment reserves also unavailable when ON_UP/ON_DOWN (has_flat)
        res_unavail = unavail
        if self._has_flat:
            res_unavail = res_unavail + on_sum
        model.add_constraint(ru <= max_p * (1 - res_unavail), f"reserves_up_max_{time}_{n}")
        model.add_constraint(rd <= max_p * (1 - res_unavail), f"reserves_down_max_{time}_{n}")

    def _add_power_bounds(self, model, obj, time):
        n = obj.name
        p = obj.power_level_var.get_value(time)
        max_p = obj.maximum_power.get_value(time)
        min_p = obj.minimum_power.get_value(time)
        q_min = obj.minimum_power.max()
        on_up = obj.on_up_var.get_value(time)
        on_down = obj.on_down_var.get_value(time)
        on_sum = on_up + on_down
        if self._has_flat:
            on_sum = on_sum + obj.on_flat_var.get_value(time)

        lb = min_p * on_sum
        ub = max_p * on_sum

        if self._has_stop:
            q_step_down = q_min / obj._T_stop
            toff = obj.turned_off.get_value(time)
            stop = obj.stop_var.get_value(time)
            lb = lb + toff * (q_min - q_step_down)
            ub = ub + stop * q_min - toff * q_step_down

        if self._has_start:
            start = obj.on_start_var.get_value(time)
            ub = ub + start * q_min

        model.add_constraint(p >= lb, f"lower_bound_{n}_{time}")
        model.add_constraint(p <= ub, f"upper_bound_{n}_{time}")

    # ── DD auxiliary constraints ──────────────────────────────────────────

    def _add_dd_constraints(self, model, obj, time, prev_time, parameters):
        n = obj.name
        max_p = obj.maximum_power.get_value(time)
        min_p = -max_p
        stop = obj.stop_var.get_value(time)
        dd_prev = obj.dd_grad_var.get_value(prev_time)
        d_prev = obj.down_grad_var.get_value(prev_time)
        model.add_constraint(dd_prev <= max_p * stop, f"DD_evol_1_{time}_{n}")
        model.add_constraint(dd_prev >= min_p * stop, f"DD_evol_2_{time}_{n}")
        model.add_constraint(dd_prev <= d_prev - min_p * (1 - stop), f"DD_evol_3_{time}_{n}")
        model.add_constraint(dd_prev >= d_prev - max_p * (1 - stop), f"DD_evol_4_{time}_{n}")

    # ── gradient constraints ──────────────────────────────────────────────

    def _add_gradient_constraints(self, model, obj, time, prev_time):
        n = obj.name
        delta_q = obj._Delta_Q
        delta_q_unc = obj._Delta_Q_unconstrained
        dq = delta_q if delta_q > 0 else delta_q_unc

        p = obj.power_level_var.get_value(time)
        p_prev = obj.power_level_var.get_value(prev_time)
        diff = p - p_prev

        ton = obj.turned_on.get_value(time)
        toff = obj.turned_off.get_value(time)

        if self._has_flat:
            entered_up_prev = obj.entered_up_var.get_value(prev_time)
            entered_down_prev = obj.entered_down_var.get_value(prev_time)
            u_prev = obj.up_grad_var.get_value(prev_time)
            d_prev = obj.down_grad_var.get_value(prev_time)
            up_base = dq * entered_up_prev + u_prev + d_prev
            down_base = -dq * entered_down_prev + u_prev + d_prev
        else:
            on_up_prev = obj.on_up_var.get_value(prev_time)
            on_down_prev = obj.on_down_var.get_value(prev_time)
            up_base = dq * on_up_prev
            down_base = -dq * on_down_prev

        q_min = obj.minimum_power.max()

        if self._has_start:
            q_step_up = q_min / obj._T_start
            start_prev = obj.on_start_var.get_value(prev_time)
            startup_contrib = q_step_up * ton + start_prev * q_step_up
            up_base = up_base + startup_contrib
            down_base = down_base + startup_contrib
        else:
            up_base = up_base + delta_q_unc * ton

        if self._has_stop:
            q_step_down = q_min / obj._T_stop
            stop_prev = obj.stop_var.get_value(prev_time)
            shutdown_contrib = -toff * q_step_down - stop_prev * q_step_down
            up_base = up_base + shutdown_contrib
            down_base = down_base + shutdown_contrib
            if self._has_flat:
                fds = obj.flat_down_stop.get_value(time)
                dd_prev = obj.dd_grad_var.get_value(prev_time)
                down_base = down_base + fds * dq - dd_prev
                up_base = up_base - dd_prev
            else:
                down_to_stop = obj.down_to_stop_grad.get_value(time)
                down_base = down_base + down_to_stop * dq
        else:
            down_base = down_base - delta_q_unc * toff

        prefix = "upward_gradient" if delta_q > 0 else "unconstrained_upward_gradient"
        suffix = "downward_gradient" if delta_q > 0 else "unconstrained_downward_gradient"

        # comb 1 (no flags): all gradient names use prev_time
        # comb 4 (has_start only): constrained use time, unconstrained use prev_time
        # all others: use time
        if not self._has_stop and not self._has_start and not self._has_flat:
            grad_time = prev_time
        elif self._has_start and not self._has_stop and not self._has_flat and delta_q == 0:
            grad_time = prev_time
        else:
            grad_time = time

        model.add_constraint(diff <= up_base, f"{prefix}_{n}_{grad_time}")
        model.add_constraint(diff >= down_base, f"{suffix}_{n}_{grad_time}")
