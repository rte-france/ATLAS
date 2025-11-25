"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

from atlas.math.timeseries import Timeseries

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO

from atlas.modules.portfolio_optimisation.models.thermal.initial_conditions_utils import (
    initialize_day_zero_core,
    initialize_day_zero_gradient_vars,
    initialize_day_zero_stable_vars,
    initialize_flat_down_stop_initial_conditions,
    initialize_gradient_initial_conditions,
)
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.solver.solver_interface import OptimisationModel


def add_initial_conditions(
    obj: ThermalPO,
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
    extended_start_date: DateTime,
    day_zero: bool,
    **kwargs,
) -> None:
    """Combination 8: T_stop>=1, T_start>=1, T_stable>=1"""
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(obj, model, time)
            initialize_day_zero_gradient_vars(obj, model, time)

            obj.flat_down_stop.set_extended(time, 0)
            obj.on_start_var.set_extended(time, 0)
            obj.stop_var.set_extended(time, 0)

        for time in kwargs.get("stable_initial_times", []):
            initialize_day_zero_stable_vars(obj, time)

    else:
        # Non-dayZero case: Initialize based on power history
        power_ts = kwargs.get("power_ts")
        if not isinstance(power_ts, Timeseries):
            raise ValueError("power_ts is required in kwargs when day_zero is False")
        if obj.minimum_power is None:
            raise ValueError("minimum_power is required when day_zero is False")

        for time in kwargs.get("initial_times", []):
            power_t = power_ts.get_value(time)
            obj.power_level_var.set_extended(time, power_t)
            min_power = obj.minimum_power.get_value(time)

            if power_t >= min_power:
                obj.off_var.set_extended(time, 0)
                obj.on_start_var.set_extended(time, 0)
                obj.stop_var.set_extended(time, 0)

            elif power_t > 0:
                obj.off_var.set_extended(time, 0)
                obj.on_start_var.set_extended(time, 1)
                obj.stop_var.set_extended(time, 1)
            else:
                obj.off_var.set_extended(time, 1)
                obj.on_start_var.set_extended(time, 0)
                obj.stop_var.set_extended(time, 0)

            obj.turned_on.set_extended(time, 0)
            obj.turned_off.set_extended(time, 0)

            prev_time = time - parameters.timestep
            prev_power = power_ts.get_value(prev_time)
            # Distinguish between startup and shutdown for intermediate power levels
            if time != extended_start_date and obj.on_start_var.get_extended_value(time) == 1:
                if power_t > prev_power:
                    obj.stop_var.set_extended(time, 0)

                elif power_t < prev_power:
                    obj.stop_var.set_extended(time, 1)
                    obj.on_start_var.set_extended(time, 0)

            if time != extended_start_date:
                if obj.stop_var.get_extended_value(time) - obj.stop_var.get_extended_value(prev_time) == 1:
                    obj.turned_off.set_extended(time, 1)

                elif obj.on_start_var.get_extended_value(time) - obj.on_start_var.get_extended_value(prev_time) == 1:
                    obj.turned_on.set_extended(time, 1)

        # Handle stable-specific variables for non-dayZero
        for idx, time in enumerate(kwargs.get("stable_initial_times", [])):
            current_power = power_ts.get_value(time)
            next_time = time + parameters.timestep
            next_power = power_ts.get_value(next_time) if next_time in power_ts else current_power
            min_power = obj.minimum_power.get_value(time)

            # Initialize auxiliary variables to 0
            obj.stable_var.set_extended(time, 0)
            obj.entered_up_var.set_extended(time, 0)
            obj.entered_down_var.set_extended(time, 0)

            # Set stable state variables based on unit state
            if obj.off_var.get_extended_value(time) == 0:
                if obj.stop_var.get_extended_value(time) == 1 or obj.on_start_var.get_extended_value(time) == 1:
                    obj.on_up_var.set_extended(time, 0)
                    obj.on_down_var.set_extended(time, 0)
                    obj.on_flat_var.set_extended(time, 0)
                else:
                    # Unit is ON and above minimum power - determine trend
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

            if time != extended_start_date and obj.off_var.get_extended_value(time) != 1:
                prev_time = time - parameters.timestep
                if obj.on_flat_var.get_extended_value(time) - obj.on_flat_var.get_extended_value(prev_time) == 1:
                    obj.stable_var.set_extended(time, 1)

                if obj.on_up_var.get_extended_value(time) - obj.on_up_var.get_extended_value(prev_time) == 1:
                    obj.entered_up_var.set_extended(time, 1)

                if obj.on_down_var.get_extended_value(time) - obj.on_down_var.get_extended_value(prev_time) == 1:
                    obj.entered_down_var.set_extended(time, 1)

            if idx >= 2:
                initialize_flat_down_stop_initial_conditions(
                    obj,
                    time - parameters.timestep,
                    time - 2 * parameters.timestep,
                    time - 3 * parameters.timestep,
                )

        initialize_gradient_initial_conditions(obj, model, power_ts, parameters)


def add_constraints(
    obj: ThermalPO, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
) -> None:
    """Add constraints for Combination 8: T_start >= 1, T_stable >= 1, T_stop >= 1"""
    if obj.minimum_power is None or obj.maximum_power is None:
        raise ValueError("minimum_power and maximum_power cannot be None")

    prev_time = time - parameters.timestep

    off_var = obj.off_var.get_value(time)
    on_up_var = obj.on_up_var.get_value(time)
    on_down_var = obj.on_down_var.get_value(time)
    on_flat_var = obj.on_flat_var.get_value(time)
    start_var = obj.on_start_var.get_value(time)
    stop_var = obj.stop_var.get_value(time)
    turned_on_var = obj.turned_on.get_value(time)
    turned_off_var = obj.turned_off.get_value(time)
    stable_var = obj.stable_var.get_value(time)
    entered_up_var = obj.entered_up_var.get_value(time)
    entered_down_var = obj.entered_down_var.get_value(time)
    flat_down_stop_var = obj.flat_down_stop.get_value(time)
    power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")

    up_grad_var = model.get_variable(f"UP_grad_{time}_{obj.name}")
    aux_up_grad_var = model.get_variable(f"aux_up_grad_{time}_{obj.name}")
    down_grad_var = model.get_variable(f"DOWN_grad_{time}_{obj.name}")
    aux_down_grad_var = model.get_variable(f"aux_down_grad_{time}_{obj.name}")

    off_prev_var = obj.off_var.get_value(prev_time)
    on_up_prev_var = obj.on_up_var.get_value(prev_time)
    on_down_prev_var = obj.on_down_var.get_value(prev_time)
    on_flat_prev_var = obj.on_flat_var.get_value(prev_time)
    start_prev_var = obj.on_start_var.get_value(prev_time)
    stop_prev_var = obj.stop_var.get_value(prev_time)
    stable_prev_var = obj.stable_var.get_value(prev_time)
    entered_up_prev_var = obj.entered_up_var.get_value(prev_time)
    entered_down_prev_var = obj.entered_down_var.get_value(prev_time)

    power_prev_var = model.get_variable(f"{obj.name}_power_level_{prev_time}")
    up_grad_prev_var = model.get_variable(f"UP_grad_{prev_time}_{obj.name}")
    down_grad_prev_var = model.get_variable(f"DOWN_grad_{prev_time}_{obj.name}")
    dd_grad_prev_var = model.get_variable(f"DD_grad_{prev_time}_{obj.name}")

    on_flat_2_prev_var = obj.on_flat_var.get_value(prev_time - parameters.timestep)
    on_down_2_prev_var = obj.on_down_var.get_value(prev_time - parameters.timestep)
    on_up_2_prev_var = obj.on_up_var.get_value(prev_time - parameters.timestep)
    stop_2_prev_var = obj.stop_var.get_value(prev_time - parameters.timestep)

    reserves_up_var = model.get_variable(f"reserves_up_{obj.name}_{time}")
    reserves_down_var = model.get_variable(f"reserves_down_{obj.name}_{time}")
    automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{obj.name}_{time}")
    automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{obj.name}_{time}")
    unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{obj.name}_{time}")
    unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{obj.name}_{time}")
    relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{obj.name}_{time}")

    max_power = obj.maximum_power.get_value(time)
    min_power = obj.minimum_power.get_value(time)
    maximum_automated = get_maximum_automated(obj)

    q_min = obj.minimum_power.max()
    q_step_up = q_min / obj._T_start
    q_step_down = q_min / obj._T_stop

    model.add_constraint(turned_on_var <= 1 - off_var, f"t_on_evol_1_{time}_{obj.name}")
    model.add_constraint(turned_on_var <= off_prev_var, f"t_on_evol_2_{time}_{obj.name}")
    model.add_constraint(turned_on_var >= off_prev_var - off_var, f"t_on_evol_3_{time}_{obj.name}")

    model.add_constraint(turned_off_var <= 1 - stop_prev_var, f"t_off_evol_1_{time}_{obj.name}")
    model.add_constraint(turned_off_var <= stop_var, f"t_off_evol_2_{time}_{obj.name}")
    model.add_constraint(turned_off_var >= stop_var - stop_prev_var, f"t_off_evol_3_{time}_{obj.name}")

    model.add_constraint(stable_var <= 1 - on_flat_prev_var, f"stable_evol_1_{time}_{obj.name}")
    model.add_constraint(stable_var <= on_flat_var, f"stable_evol_2_{time}_{obj.name}")
    model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var, f"stable_evol_3_{time}_{obj.name}")

    if time == parameters.start_date:
        model.add_constraint(stable_prev_var <= on_flat_2_prev_var, f"stable_evol_1_{prev_time}_{obj.name}")
        model.add_constraint(stable_prev_var <= on_flat_prev_var, f"stable_evol_2_{prev_time}_{obj.name}")
        model.add_constraint(
            stable_prev_var >= on_flat_prev_var - on_flat_2_prev_var, f"stable_evol_3_{prev_time}_{obj.name}"
        )

        model.add_constraint(entered_up_prev_var <= 1 - on_up_2_prev_var, f"entered_up_evol_1_{prev_time}_{obj.name}")
        model.add_constraint(entered_up_prev_var <= on_up_prev_var, f"entered_up_evol_2_{prev_time}_{obj.name}")
        model.add_constraint(
            entered_up_prev_var >= on_up_prev_var - on_up_2_prev_var, f"entered_up_evol_3_{prev_time}_{obj.name}"
        )

        model.add_constraint(
            entered_down_prev_var <= 1 - on_down_2_prev_var, f"entered_down_evol_1_{prev_time}_{obj.name}"
        )
        model.add_constraint(entered_down_prev_var <= on_down_prev_var, f"entered_down_evol_2_{prev_time}_{obj.name}")
        model.add_constraint(
            entered_down_prev_var >= on_down_prev_var - on_down_2_prev_var,
            f"entered_down_evol_3_{prev_time}_{obj.name}",
        )

        model.add_constraint(
            off_prev_var + on_up_prev_var + on_down_prev_var + on_flat_prev_var + stop_prev_var + start_prev_var == 1,
            f"mutual_exclusion_{prev_time}_{obj.name}",
        )

        model.add_constraint(
            on_up_2_prev_var + on_down_prev_var <= 1, f"transition_constraint_1_{prev_time}_{obj.name}"
        )
        model.add_constraint(
            on_down_2_prev_var + on_up_prev_var <= 1, f"transition_constraint_2_{prev_time}_{obj.name}"
        )
        model.add_constraint(stop_2_prev_var + on_flat_prev_var <= 1, f"transition_constraint_3_{prev_time}_{obj.name}")
        model.add_constraint(stop_2_prev_var + on_down_prev_var <= 1, f"transition_constraint_4_{prev_time}_{obj.name}")
        model.add_constraint(stop_2_prev_var + on_up_prev_var <= 1, f"transition_constraint_5_{prev_time}_{obj.name}")

    model.add_constraint(flat_down_stop_var <= stop_var, f"flat_down_stop_1_{time}_{obj.name}")
    model.add_constraint(flat_down_stop_var <= on_down_prev_var, f"flat_down_stop_2_{time}_{obj.name}")
    model.add_constraint(flat_down_stop_var <= on_flat_2_prev_var, f"flat_down_stop_3_{time}_{obj.name}")
    model.add_constraint(
        flat_down_stop_var >= stop_var + on_down_prev_var + on_flat_2_prev_var - 2,
        f"flat_down_stop_4_{time}_{obj.name}",
    )

    model.add_constraint(entered_up_var <= 1 - on_up_prev_var, f"entered_up_evol_1_{time}_{obj.name}")
    model.add_constraint(entered_up_var <= on_up_var, f"entered_up_evol_2_{time}_{obj.name}")
    model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var, f"entered_up_evol_3_{time}_{obj.name}")

    model.add_constraint(entered_down_var <= 1 - on_down_prev_var, f"entered_down_evol_1_{time}_{obj.name}")
    model.add_constraint(entered_down_var <= on_down_var, f"entered_down_evol_2_{time}_{obj.name}")
    model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var, f"entered_down_evol_3_{time}_{obj.name}")

    model.add_constraint(aux_up_grad_var <= max_power * on_up_prev_var, f"tilde_U_evol_1_{time}_{obj.name}")
    model.add_constraint(aux_up_grad_var >= min_power * on_up_prev_var, f"tilde_U_evol_2_{time}_{obj.name}")
    model.add_constraint(
        aux_up_grad_var <= power_level_var - power_prev_var - min_power * (1 - on_up_prev_var),
        f"tilde_U_evol_3_{time}_{obj.name}",
    )
    model.add_constraint(
        aux_up_grad_var >= power_level_var - power_prev_var - max_power * (1 - on_up_prev_var),
        f"tilde_U_evol_4_{time}_{obj.name}",
    )

    model.add_constraint(aux_down_grad_var <= max_power * on_down_prev_var, f"tilde_D_evol_1_{time}_{obj.name}")
    model.add_constraint(aux_down_grad_var >= min_power * on_down_prev_var, f"tilde_D_evol_2_{time}_{obj.name}")
    model.add_constraint(
        aux_down_grad_var <= power_level_var - power_prev_var - min_power * (1 - on_down_prev_var),
        f"tilde_D_evol_3_{time}_{obj.name}",
    )
    model.add_constraint(
        aux_down_grad_var >= power_level_var - power_prev_var - max_power * (1 - on_down_prev_var),
        f"tilde_D_evol_4_{time}_{obj.name}",
    )

    model.add_constraint(up_grad_var <= max_power * on_up_var, f"U_evol_1_{time}_{obj.name}")
    model.add_constraint(up_grad_var >= min_power * on_up_var, f"U_evol_2_{time}_{obj.name}")
    model.add_constraint(up_grad_var <= aux_up_grad_var - min_power * (1 - on_up_var), f"U_evol_3_{time}_{obj.name}")
    model.add_constraint(up_grad_var >= aux_up_grad_var - max_power * (1 - on_up_var), f"U_evol_4_{time}_{obj.name}")

    model.add_constraint(down_grad_var <= max_power * on_down_var, f"D_evol_1_{time}_{obj.name}")
    model.add_constraint(down_grad_var >= min_power * on_down_var, f"D_evol_2_{time}_{obj.name}")
    model.add_constraint(
        down_grad_var <= aux_down_grad_var - min_power * (1 - on_down_var), f"D_evol_3_{time}_{obj.name}"
    )
    model.add_constraint(
        down_grad_var >= aux_down_grad_var - max_power * (1 - on_down_var), f"D_evol_4_{time}_{obj.name}"
    )

    if time in obj.optimisation_time_window[:-1]:
        model.add_constraint(dd_grad_prev_var <= max_power * stop_var, f"DD_evol_1_{time}_{obj.name}")
        model.add_constraint(dd_grad_prev_var >= min_power * stop_var, f"DD_evol_2_{time}_{obj.name}")
        model.add_constraint(
            dd_grad_prev_var <= down_grad_prev_var - min_power * (1 - stop_var), f"DD_evol_3_{time}_{obj.name}"
        )
        model.add_constraint(
            dd_grad_prev_var >= down_grad_prev_var - max_power * (1 - stop_var), f"DD_evol_4_{time}_{obj.name}"
        )

    model.add_constraint(
        off_var + on_up_var + on_down_var + on_flat_var + stop_var + start_var == 1,
        f"mutual_exclusion_{time}_{obj.name}",
    )

    model.add_constraint(on_up_prev_var + on_down_var <= 1, f"transition_constraint_1_{time}_{obj.name}")
    model.add_constraint(on_down_prev_var + on_up_var <= 1, f"transition_constraint_2_{time}_{obj.name}")
    model.add_constraint(stop_prev_var + on_flat_var <= 1, f"transition_constraint_3_{time}_{obj.name}")
    model.add_constraint(stop_prev_var + on_down_var <= 1, f"transition_constraint_4_{time}_{obj.name}")
    model.add_constraint(stop_prev_var + on_up_var <= 1, f"transition_constraint_5_{time}_{obj.name}")
    model.add_constraint(on_up_prev_var + stop_var <= 1, f"transition_constraint_6_{time}_{obj.name}")
    model.add_constraint(off_prev_var + stop_var <= 1, f"transition_constraint_7_{time}_{obj.name}")
    model.add_constraint(on_up_prev_var + start_var <= 1, f"transition_constraint_8_{time}_{obj.name}")
    model.add_constraint(on_down_prev_var + start_var <= 1, f"transition_constraint_9_{time}_{obj.name}")
    model.add_constraint(on_flat_prev_var + start_var <= 1, f"transition_constraint_10_{time}_{obj.name}")
    model.add_constraint(on_up_prev_var + off_var <= 1, f"transition_constraint_11_{time}_{obj.name}")
    model.add_constraint(on_down_prev_var + off_var <= 1, f"transition_constraint_12_{time}_{obj.name}")
    model.add_constraint(on_flat_prev_var + off_var <= 1, f"transition_constraint_13_{time}_{obj.name}")
    model.add_constraint(start_prev_var + off_var <= 1, f"transition_constraint_14_{time}_{obj.name}")
    model.add_constraint(start_prev_var + stop_var <= 1, f"transition_constraint_15_{time}_{obj.name}")
    model.add_constraint(stop_prev_var + start_var <= 1, f"transition_constraint_16_{time}_{obj.name}")
    model.add_constraint(off_prev_var + on_up_var <= 1, f"transition_constraint_17_{time}_{obj.name}")
    model.add_constraint(off_prev_var + on_flat_var <= 1, f"transition_constraint_18_{time}_{obj.name}")
    model.add_constraint(off_prev_var + on_down_var <= 1, f"transition_constraint_19_{time}_{obj.name}")

    stop_eviction_time = time - (obj._T_stop - 1) * parameters.timestep
    turned_off_stop_eviction_var = obj.turned_off.get_value(stop_eviction_time)
    model.add_constraint(turned_off_stop_eviction_var + stop_var <= 1, f"stop_eviction_constraint_{time}_{obj.name}")

    start_eviction_time = time - (obj._T_start - 1) * parameters.timestep
    turned_on_start_eviction_var = obj.turned_on.get_value(start_eviction_time)
    model.add_constraint(
        turned_on_start_eviction_var + start_var <= 1, f"start_eviction_constraint_18_{time}_{obj.name}"
    )

    if obj._T_on >= 2:
        for s in range(1, obj._T_on):
            local_time = time - (s + obj._T_start) * parameters.timestep
            turned_on_local_var = obj.turned_on.get_value(local_time)
            model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

    if obj._T_off >= 2:
        for s in range(1, obj._T_off):
            local_time = time - (s + obj._T_stop) * parameters.timestep
            turned_off_local_var = obj.turned_off.get_value(local_time)
            model.add_constraint(turned_off_local_var <= off_var)

    if obj._T_stable >= 2:
        for s in range(1, obj._T_stable - 1):
            local_time = time - s * parameters.timestep
            stable_local_var = obj.stable_var.get_value(local_time)
            model.add_constraint(stable_local_var <= on_flat_var)

    if obj._T_stop >= 2:
        for s in range(1, obj._T_stop - 1):
            local_time = time - s * parameters.timestep
            turned_off_local_var = obj.turned_off.get_value(local_time)
            model.add_constraint(turned_off_local_var <= stop_var)

    if obj._T_start >= 2:
        for s in range(1, obj._T_start):
            local_time = time - s * parameters.timestep
            turned_on_local_var = obj.turned_on.get_value(local_time)
            model.add_constraint(turned_on_local_var <= start_var)

    model.add_constraint(
        power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
        <= max_power + parameters.allowed_round_off_error
    )
    model.add_constraint(
        power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
        >= max_power - parameters.allowed_round_off_error
    )

    model.add_constraint(
        power_level_var
        - reserves_down_var
        - automated_reserves_down_var
        - unprovided_reserves_down_var
        + relaxed_reserves_var
        <= min_power + parameters.allowed_round_off_error
    )
    model.add_constraint(
        power_level_var
        - reserves_down_var
        - automated_reserves_down_var
        - unprovided_reserves_down_var
        + relaxed_reserves_var
        >= min_power - parameters.allowed_round_off_error
    )

    model.add_constraint(relaxed_reserves_var <= min_power * (1 - on_up_var - on_flat_var - on_down_var))

    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var - stop_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var - stop_var))
    model.add_constraint(reserves_up_var <= max_power * (1 - on_up_var - on_down_var - off_var - start_var - stop_var))
    model.add_constraint(
        reserves_down_var <= max_power * (1 - on_up_var - on_down_var - off_var - start_var - stop_var)
    )

    model.add_constraint(
        power_level_var >= min_power * (on_up_var + on_down_var + on_flat_var) + turned_off_var * (q_min - q_step_down)
    )

    model.add_constraint(
        power_level_var
        <= max_power * (on_up_var + on_down_var + on_flat_var)
        + (stop_var + start_var) * q_min
        - turned_off_var * q_step_down
    )

    # Power gradients with all auxiliary variables - most complex gradient logic
    if time in obj.optimisation_time_window[:-1]:  # Not the last time step
        if obj._Delta_Q > 0:  # Finite gradient
            # Upward gradient - eq. (33)
            model.add_constraint(
                power_level_var - power_prev_var
                <= obj._Delta_Q * entered_up_var
                + up_grad_prev_var
                + down_grad_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + (turned_on_var + start_prev_var) * q_step_up
                - dd_grad_prev_var
            )
            # Downward gradient - eq. (35)
            model.add_constraint(
                power_level_var - power_prev_var
                >= -obj._Delta_Q * entered_down_var
                + up_grad_prev_var
                + down_grad_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + flat_down_stop_var * obj._Delta_Q
                - dd_grad_prev_var
                + (turned_on_var + start_prev_var) * q_step_up
            )
        elif obj._Delta_Q == 0:  # Infinite gradient
            # Upward unconstrained gradient - eq. (34)
            model.add_constraint(
                power_level_var - power_prev_var
                <= obj._Delta_Q_unconstrained * entered_up_var
                + up_grad_prev_var
                + down_grad_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + (turned_on_var + start_prev_var) * q_step_up
                - dd_grad_prev_var
            )
            # Downward unconstrained gradient - eq. (36)
            model.add_constraint(
                power_level_var - power_prev_var
                >= -obj._Delta_Q_unconstrained * entered_down_var
                + up_grad_prev_var
                + down_grad_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + flat_down_stop_var * obj._Delta_Q_unconstrained
                - dd_grad_prev_var
                + (turned_on_var + start_prev_var) * q_step_up
            )
