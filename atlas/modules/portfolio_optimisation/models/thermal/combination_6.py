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
    """Combination 6: T_stop=0, T_start>=1, T_stable>=1"""
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(obj, model, time)
            initialize_day_zero_gradient_vars(obj, model, time)

            obj.on_start_var.set_extended(time, 0)

        for time in kwargs.get("stable_initial_times", []):
            initialize_day_zero_stable_vars(obj, model, time)

    else:
        # Non-dayZero case: Initialize based on power history
        power_timeseries = kwargs.get("power_timeseries")
        if not isinstance(power_timeseries, Timeseries):
            raise ValueError("power_timeseries is required in kwargs when day_zero is False")
        if obj.minimum_power is None:
            raise ValueError("minimum_power is required when day_zero is False")

        for time in kwargs.get("initial_times", []):
            power_at_time = power_timeseries.get_value(time)
            min_power = obj.minimum_power.get_value(time)

            if power_at_time >= min_power:
                obj.off_var.set_extended(time, 0)
                obj.on_start_var.set_extended(time, 0)

            elif power_at_time > 0:
                obj.off_var.set_extended(time, 0)
                obj.on_start_var.set_extended(time, 1)
            else:
                obj.off_var.set_extended(time, 1)
                obj.on_start_var.set_extended(time, 0)

            obj.turned_on.set_extended(time, 0)
            obj.turned_off.set_extended(time, 0)

            if time != extended_start_date:
                prev_time = time - parameters.timestep

                if obj.off_var.get_extended_value(time) - obj.off_var.get_extended_value(prev_time) == 1:
                    obj.turned_off.set_extended(time, 1)

                elif obj.on_start_var.get_extended_value(time) - obj.on_start_var.get_extended_value(prev_time) == 1:
                    obj.turned_on.set_extended(time, 1)

        for time in kwargs.get("stable_initial_times", []):
            current_power = power_timeseries.get_value(time)
            next_power = power_timeseries.get_value(time + parameters.timestep)
            min_power = obj.minimum_power.get_value(time)

            obj.stable_var.set_extended(time, 0)
            obj.entered_up_var.set_extended(time, 0)
            obj.entered_down_var.set_extended(time, 0)

            if obj.off_var.get_extended_value(time) == 0:
                if obj.on_start_var.get_extended_value(time) == 1:
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

        initialize_gradient_initial_conditions(obj, model, power_timeseries, parameters)


def add_constraints(
    obj: ThermalPO, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
) -> None:
    """Add constraints for Combination 6:  T_stop=0, T_start>=1, T_stable>=1"""
    if obj.minimum_power is None or obj.maximum_power is None:
        raise ValueError("minimum_power and maximum_power cannot be None")

    prev_time = time - parameters.timestep

    off_var = obj.off_var.get_value(time)
    on_up_var = obj.on_up_var.get_value(time)
    on_down_var = obj.on_down_var.get_value(time)
    on_flat_var = obj.on_flat_var.get_value(time)

    start_var = obj.on_start_var.get_value(time)
    turned_on_var = obj.turned_on.get_value(time)
    turned_off_var = obj.turned_off.get_value(time)
    stable_var = obj.stable_var.get_value(time)
    entered_up_var = obj.entered_up_var.get_value(time)
    entered_down_var = obj.entered_down_var.get_value(time)
    power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")

    up_grad_var = model.get_variable(f"UP_grad_{time}_{obj.name}")
    aux_up_grad_var = model.get_variable(f"aux_up_grad_{time}_{obj.name}")
    down_grad_var = model.get_variable(f"DOWN_grad_{time}_{obj.name}")
    aux_down_grad_var = model.get_variable(f"aux_down_grad_{time}_{obj.name}")
    up_grad_prev_var = model.get_variable(f"UP_grad_{prev_time}_{obj.name}")
    down_grad_prev_var = model.get_variable(f"DOWN_grad_{prev_time}_{obj.name}")

    off_prev_var = obj.off_var.get_value(prev_time)
    on_up_prev_var = obj.on_up_var.get_value(prev_time)
    on_down_prev_var = obj.on_down_var.get_value(prev_time)
    on_flat_prev_var = obj.on_flat_var.get_value(prev_time)
    stable_prev_var = obj.stable_var.get_value(prev_time)
    entered_up_prev_var = obj.entered_up_var.get_value(prev_time)
    entered_down_prev_var = obj.entered_down_var.get_value(prev_time)
    start_prev_var = obj.on_start_var.get_value(prev_time)
    power_level_prev_var = model.get_variable(f"{obj.name}_power_level_{prev_time}")

    on_flat_2_prev_var = obj.on_flat_var.get_value(prev_time - parameters.timestep)
    on_up_2_prev_var = obj.on_up_var.get_value(prev_time - parameters.timestep)
    on_down_2_prev_var = obj.on_down_var.get_value(prev_time - parameters.timestep)

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
    q_step = q_min / obj._T_start

    model.add_constraint(turned_on_var <= 1 - off_var)
    model.add_constraint(turned_on_var <= off_prev_var)
    model.add_constraint(turned_on_var >= off_prev_var - off_var)

    model.add_constraint(turned_off_var <= 1 - off_prev_var)
    model.add_constraint(turned_off_var <= off_var)
    model.add_constraint(turned_off_var >= off_var - off_prev_var)

    model.add_constraint(stable_var <= 1 - on_flat_prev_var)
    model.add_constraint(stable_var <= on_flat_var)
    model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var)

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

        model.add_constraint(off_prev_var + on_up_prev_var + on_down_prev_var + on_flat_prev_var + start_prev_var == 1)

        model.add_constraint(on_up_2_prev_var + on_down_prev_var <= 1)
        model.add_constraint(on_down_2_prev_var + on_up_prev_var <= 1)

    model.add_constraint(entered_up_var <= 1 - on_up_prev_var)
    model.add_constraint(entered_up_var <= on_up_var)
    model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var)

    model.add_constraint(entered_down_var <= 1 - on_down_prev_var)
    model.add_constraint(entered_down_var <= on_down_var)
    model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var)

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

    model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var + start_var == 1)

    model.add_constraint(on_up_prev_var + on_down_var <= 1)
    model.add_constraint(on_down_prev_var + on_up_var <= 1)

    model.add_constraint(on_up_prev_var + start_var <= 1)
    model.add_constraint(on_down_prev_var + start_var <= 1)
    model.add_constraint(on_flat_prev_var + start_var <= 1)

    model.add_constraint(off_var + start_prev_var <= 1)

    model.add_constraint(off_prev_var + on_flat_var <= 1)
    model.add_constraint(off_prev_var + on_down_var <= 1)
    model.add_constraint(off_prev_var + on_up_var <= 1)

    eviction_time = time - (obj._T_start - 1) * parameters.timestep
    turned_on_eviction_var = model.get_variable(f"t_on_of_{obj.name}_{eviction_time}")
    model.add_constraint(turned_on_eviction_var + start_var <= 1)

    # Minimum time constraints
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

    # Shutdown ramp constraints - eq. (24)
    if obj._T_start >= 2:
        for s in range(1, obj._T_stop - 1):
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

    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var))

    model.add_constraint(reserves_up_var <= max_power * (1 - on_up_var - on_down_var - off_var - start_var))
    model.add_constraint(reserves_down_var <= max_power * (1 - on_up_var - on_down_var - off_var - start_var))

    model.add_constraint(power_level_var >= min_power * (on_up_var + on_down_var + on_flat_var))

    model.add_constraint(power_level_var <= max_power * (on_up_var + on_down_var + on_flat_var) + start_var * q_min)

    if time in obj.optimisation_time_window[:-1]:
        if obj._Delta_Q > 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q * entered_up_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                + q_step * (turned_on_var + start_var)
            )

            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q * entered_down_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                - obj._Delta_Q_unconstrained * turned_off_var
                + (turned_on_var + start_var) * q_step
            )
        elif obj._Delta_Q == 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q_unconstrained * entered_up_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                + q_step * (turned_on_var + start_var)
            )

            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q_unconstrained * entered_down_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                - obj._Delta_Q_unconstrained * turned_off_var
                + (start_prev_var + turned_on_var) * q_step
            )
