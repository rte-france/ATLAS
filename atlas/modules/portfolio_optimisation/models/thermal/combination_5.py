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
    """Combination 5: T_stop>=1, T_start=0, T_stable>=1"""
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(obj, model, time)
            initialize_day_zero_gradient_vars(obj, model, time)

            obj.flat_down_stop.set_extended(time, 0)
            obj.stop_var.set_extended(time, 0)

        for time in kwargs.get("stable_initial_times", []):
            initialize_day_zero_stable_vars(obj, time)

        power_ts = kwargs.get("power_ts")
        if isinstance(power_ts, Timeseries):
            initialize_gradient_initial_conditions(obj, model, power_ts, parameters)

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
                obj.stop_var.set_extended(time, 0)

            elif power_t > 0:
                obj.off_var.set_extended(time, 0)
                obj.stop_var.set_extended(time, 1)
            else:
                obj.off_var.set_extended(time, 1)
                obj.stop_var.set_extended(time, 0)

            obj.turned_off.set_extended(time, 0)
            obj.turned_on.set_extended(time, 0)
            obj.flat_down_stop.set_extended(time, 0)

            if time != extended_start_date:
                prev_time = time - parameters.timestep
                if obj.stop_var.get_extended_value(time) - obj.stop_var.get_extended_value(prev_time) == 1:
                    obj.turned_off.set_extended(time, 1)

                elif obj.off_var.get_extended_value(time) - obj.off_var.get_extended_value(prev_time) == -1:
                    obj.turned_on.set_extended(time, 1)

        for idx, time in enumerate(kwargs.get("stable_initial_times", [])):
            current_power = power_ts.get_value(time)
            next_power = power_ts.get_value(time + parameters.timestep)

            obj.stable_var.set_extended(time, 0)
            obj.entered_up_var.set_extended(time, 0)
            obj.entered_down_var.set_extended(time, 0)

            if obj.off_var.get_extended_value(time) == 0:
                if obj.stop_var.get_extended_value(time) == 1:
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
        initialize_flat_down_stop_initial_conditions(
            obj,
            parameters.start_date - parameters.timestep,
            parameters.start_date - 2 * parameters.timestep,
            parameters.start_date - 3 * parameters.timestep,
        )


def add_constraints(
    obj: ThermalPO, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
) -> None:
    """Add constraints for Combination 5: T_start = 0, T_stable >= 1, T_stop >= 1"""
    if obj.minimum_power is None or obj.maximum_power is None:
        raise ValueError("minimum_power and maximum_power cannot be None")

    prev_time = time - parameters.timestep

    # Get variables
    off_var = obj.off_var.get_value(time)
    on_up_var = obj.on_up_var.get_value(time)
    on_down_var = obj.on_down_var.get_value(time)
    on_flat_var = obj.on_flat_var.get_value(time)
    stop_var = obj.stop_var.get_value(time)
    turned_on_var = obj.turned_on.get_value(time)
    turned_off_var = obj.turned_off.get_value(time)
    stable_var = obj.stable_var.get_value(time)
    entered_up_var = obj.entered_up_var.get_value(time)
    entered_down_var = obj.entered_down_var.get_value(time)
    flat_down_stop_var = obj.flat_down_stop.get_value(time)
    power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")

    up_grad_var = model.get_variable(f"UP_grad_{time}_{obj.name}")
    up_grad_prev_var = model.get_variable(f"UP_grad_{prev_time}_{obj.name}")
    aux_up_grad_var = model.get_variable(f"aux_up_grad_{time}_{obj.name}")
    down_grad_var = model.get_variable(f"DOWN_grad_{time}_{obj.name}")
    down_grad_prev_var = model.get_variable(f"DOWN_grad_{prev_time}_{obj.name}")
    aux_down_grad_var = model.get_variable(f"aux_down_grad_{time}_{obj.name}")
    dd_grad_prev_var = model.get_variable(f"DD_grad_{prev_time}_{obj.name}")

    off_prev_var = obj.off_var.get_value(prev_time)
    on_up_prev_var = obj.on_up_var.get_value(prev_time)
    on_up_2_prev_var = obj.off_var.get_value(prev_time - parameters.timestep)
    on_down_prev_var = obj.on_down_var.get_value(prev_time)
    on_down_2_prev_var = obj.on_down_var.get_value(prev_time - parameters.timestep)
    on_flat_prev_var = obj.on_flat_var.get_value(prev_time)
    stop_prev_var = obj.stop_var.get_value(prev_time)
    stop_2_prev_var = obj.stop_var.get_value(prev_time - parameters.timestep)
    stable_prev_var = obj.stable_var.get_value(prev_time)
    entered_down_prev_var = obj.entered_down_var.get_value(prev_time)
    entered_up_prev_var = obj.entered_up_var.get_value(prev_time)
    on_flat_2_prev_var = obj.on_flat_var.get_value(prev_time - parameters.timestep)
    power_level_prev_var = model.get_variable(f"{obj.name}_power_level_{prev_time}")

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
    q_step = q_min / obj._T_stop

    model.add_constraint(turned_on_var <= 1 - off_var)
    model.add_constraint(turned_on_var <= off_prev_var)
    model.add_constraint(turned_on_var >= off_prev_var - off_var)

    model.add_constraint(turned_off_var <= 1 - stop_prev_var)
    model.add_constraint(turned_off_var <= stop_var)
    model.add_constraint(turned_off_var >= stop_var - stop_prev_var)

    model.add_constraint(stable_var <= 1 - on_flat_prev_var)
    model.add_constraint(stable_var <= on_flat_var)
    model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var)

    model.add_constraint(flat_down_stop_var <= stop_var)
    model.add_constraint(flat_down_stop_var <= on_down_prev_var)
    model.add_constraint(flat_down_stop_var <= on_flat_2_prev_var)
    model.add_constraint(flat_down_stop_var >= stop_var + on_down_prev_var + on_flat_2_prev_var - 2)

    model.add_constraint(entered_up_var <= 1 - on_up_prev_var)
    model.add_constraint(entered_up_var <= on_up_var)
    model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var)

    model.add_constraint(entered_down_var <= 1 - on_down_prev_var)
    model.add_constraint(entered_down_var <= on_down_var)
    model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var)

    model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var + stop_var == 1)

    model.add_constraint(on_up_prev_var + on_down_var <= 1)
    model.add_constraint(on_down_prev_var + on_up_var <= 1)
    model.add_constraint(on_up_prev_var + off_var <= 1)
    model.add_constraint(on_down_prev_var + off_var <= 1)

    model.add_constraint(stop_prev_var + on_flat_var <= 1)
    model.add_constraint(stop_prev_var + on_down_var <= 1)
    model.add_constraint(stop_prev_var + on_up_var <= 1)

    model.add_constraint(on_up_prev_var + stop_var <= 1)
    model.add_constraint(off_prev_var + stop_var <= 1)

    eviction_time = time - (obj._T_stop - 1) * parameters.timestep
    turned_off_eviction_var = obj.turned_off.get_value(eviction_time)
    model.add_constraint(turned_off_eviction_var + stop_var <= 1)

    if obj._T_on >= 2:
        for s in range(1, obj._T_on):
            local_time = time - s * parameters.timestep
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

    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - stop_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - stop_var))

    model.add_constraint(reserves_up_var <= max_power * (1 - on_up_var - on_down_var - off_var - stop_var))
    model.add_constraint(reserves_down_var <= max_power * (1 - on_up_var - on_down_var - off_var - stop_var))

    model.add_constraint(
        power_level_var >= min_power * (on_up_var + on_down_var + on_flat_var) + turned_off_var * (q_min - q_step)
    )

    model.add_constraint(
        power_level_var
        <= max_power * (on_up_var + on_down_var + on_flat_var) + stop_var * q_min - turned_off_var * q_step
    )

    model.add_constraint(aux_up_grad_var <= max_power * on_up_prev_var)
    model.add_constraint(aux_up_grad_var >= min_power * on_up_prev_var)
    model.add_constraint(aux_up_grad_var <= power_level_var - power_level_prev_var - min_power * (1 - on_up_prev_var))
    model.add_constraint(aux_up_grad_var >= power_level_var - power_level_prev_var - max_power * (1 - on_up_prev_var))

    model.add_constraint(aux_down_grad_var <= max_power * on_down_prev_var)
    model.add_constraint(aux_down_grad_var >= min_power * on_down_prev_var)
    model.add_constraint(
        aux_down_grad_var <= power_level_var - power_level_prev_var - min_power * (1 - on_down_prev_var)
    )
    model.add_constraint(
        aux_down_grad_var >= power_level_var - power_level_prev_var - max_power * (1 - on_down_prev_var)
    )

    model.add_constraint(up_grad_var <= max_power * on_up_var)
    model.add_constraint(up_grad_var >= min_power * on_up_var)
    model.add_constraint(up_grad_var <= aux_up_grad_var - min_power * (1 - on_up_var))
    model.add_constraint(up_grad_var >= aux_up_grad_var - max_power * (1 - on_up_var))

    model.add_constraint(down_grad_var <= max_power * on_down_var)
    model.add_constraint(down_grad_var >= min_power * on_down_var)
    model.add_constraint(down_grad_var <= aux_down_grad_var - min_power * (1 - on_down_var))
    model.add_constraint(down_grad_var >= aux_down_grad_var - max_power * (1 - on_down_var))

    if time == obj.optimisation_time_window[0]:
        model.add_constraint(stable_prev_var <= 1 - on_flat_2_prev_var)
        model.add_constraint(stable_prev_var <= on_flat_prev_var)
        model.add_constraint(stable_prev_var >= on_flat_prev_var - on_flat_2_prev_var)

        model.add_constraint(entered_up_prev_var <= 1 - on_up_2_prev_var)
        model.add_constraint(entered_up_prev_var <= on_up_prev_var)
        model.add_constraint(entered_up_prev_var >= on_up_prev_var - on_up_2_prev_var)

        model.add_constraint(entered_down_prev_var <= 1 - on_down_2_prev_var)
        model.add_constraint(entered_down_prev_var <= on_down_prev_var)
        model.add_constraint(entered_down_prev_var >= on_down_prev_var - on_down_2_prev_var)

        model.add_constraint(off_prev_var + on_up_prev_var + on_down_prev_var + on_flat_prev_var + stop_prev_var == 1)

        model.add_constraint(on_up_2_prev_var + on_down_prev_var <= 1)
        model.add_constraint(on_down_2_prev_var + on_up_prev_var <= 1)

        model.add_constraint(stop_2_prev_var + on_flat_prev_var <= 1)
        model.add_constraint(stop_2_prev_var + on_down_prev_var <= 1)
        model.add_constraint(stop_2_prev_var + on_up_prev_var <= 1)

    if time in obj.optimisation_time_window[:-1]:
        model.add_constraint(dd_grad_prev_var <= max_power * stop_var)
        model.add_constraint(dd_grad_prev_var >= min_power * stop_var)
        model.add_constraint(dd_grad_prev_var <= down_grad_prev_var - min_power * (1 - stop_var))
        model.add_constraint(dd_grad_prev_var >= down_grad_prev_var - max_power * (1 - stop_var))

        if obj._Delta_Q > 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q * entered_up_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                - q_step * (turned_off_var + stop_prev_var)
                + obj._Delta_Q_unconstrained * turned_on_var
                - dd_grad_prev_var
            )

            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q * entered_down_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                - q_step * (turned_off_var + stop_prev_var)
                + obj._Delta_Q * flat_down_stop_var
                - dd_grad_prev_var
            )
        elif obj._Delta_Q == 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q_unconstrained * entered_up_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                - q_step * (turned_off_var + stop_prev_var)
                + obj._Delta_Q_unconstrained * turned_on_var
            )

            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q_unconstrained * entered_down_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                - q_step * (turned_off_var + stop_prev_var)
                + flat_down_stop_var * obj._Delta_Q_unconstrained
                - dd_grad_prev_var
            )
