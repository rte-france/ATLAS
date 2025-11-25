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
from atlas.modules.portfolio_optimisation.parameters import (
    PortfolioOptimisationParameters,
)
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

            elif power_t > 0:
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
            current_power = power_ts.get_value(time)
            next_power = power_ts.get_value(time + parameters.timestep)
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

        initialize_gradient_initial_conditions(obj, model, power_ts, parameters)


def add_constraints(
    obj: ThermalPO,
    time: DateTime,
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
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
    power_level_var = obj.power_level_var.get_value(time)

    up_grad_var = obj.up_grad_var.get_value(time)
    aux_up_grad_var = obj.aux_up_grad_var.get_value(time)
    down_grad_var = obj.down_grad_var.get_value(time)
    aux_down_grad_var = obj.aux_down_grad_var.get_value(time)
    up_grad_prev_var = obj.up_grad_var.get_value(prev_time)
    down_grad_prev_var = obj.down_grad_var.get_value(prev_time)

    off_prev_var = obj.off_var.get_value(prev_time)
    on_up_prev_var = obj.on_up_var.get_value(prev_time)
    on_down_prev_var = obj.on_down_var.get_value(prev_time)
    on_flat_prev_var = obj.on_flat_var.get_value(prev_time)
    stable_prev_var = obj.stable_var.get_value(prev_time)
    entered_up_prev_var = obj.entered_up_var.get_value(prev_time)
    entered_down_prev_var = obj.entered_down_var.get_value(prev_time)
    start_prev_var = obj.on_start_var.get_value(prev_time)
    power_level_prev_var = obj.power_level_var.get_value(prev_time)

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

    model.add_constraint(turned_on_var <= 1 - off_var, f"t_on_evol_1_{time}_{obj.name}")
    model.add_constraint(turned_on_var <= off_prev_var, f"t_on_evol_2_{time}_{obj.name}")
    model.add_constraint(turned_on_var >= off_prev_var - off_var, f"t_on_evol_3_{time}_{obj.name}")

    model.add_constraint(turned_off_var <= 1 - off_prev_var, f"t_off_evol_1_{time}_{obj.name}")
    model.add_constraint(turned_off_var <= off_var, f"t_off_evol_2_{time}_{obj.name}")
    model.add_constraint(turned_off_var >= off_var - off_prev_var, f"t_off_evol_3_{time}_{obj.name}")

    model.add_constraint(stable_var <= 1 - on_flat_prev_var, f"stable_evol_1_{time}_{obj.name}")
    model.add_constraint(stable_var <= on_flat_var, f"stable_evol_2_{time}_{obj.name}")
    model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var, f"stable_evol_3_{time}_{obj.name}")

    if time == parameters.start_date:
        model.add_constraint(
            stable_prev_var <= 1 - on_flat_2_prev_var,
            f"stable_evol_1_{prev_time}_{obj.name}",
        )
        model.add_constraint(stable_prev_var <= on_flat_prev_var, f"stable_evol_2_{prev_time}_{obj.name}")
        model.add_constraint(
            stable_prev_var >= on_flat_prev_var - on_flat_2_prev_var,
            f"stable_evol_3_{prev_time}_{obj.name}",
        )

        model.add_constraint(
            entered_up_prev_var <= 1 - on_up_2_prev_var,
            f"entered_up_evol_1_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            entered_up_prev_var <= on_up_prev_var,
            f"entered_up_evol_2_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            entered_up_prev_var >= on_up_prev_var - on_up_2_prev_var,
            f"entered_up_evol_3_{prev_time}_{obj.name}",
        )

        model.add_constraint(
            entered_down_prev_var <= 1 - on_down_2_prev_var,
            f"entered_down_evol_1_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            entered_down_prev_var <= on_down_prev_var,
            f"entered_down_evol_2_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            entered_down_prev_var >= on_down_prev_var - on_down_2_prev_var,
            f"entered_down_evol_3_{prev_time}_{obj.name}",
        )

        model.add_constraint(
            off_prev_var + on_up_prev_var + on_down_prev_var + on_flat_prev_var + start_prev_var == 1,
            f"mutual_exclusion_{prev_time}_{obj.name}",
        )

        model.add_constraint(
            on_up_2_prev_var + on_down_prev_var <= 1,
            f"transition_constraint_1_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            on_down_2_prev_var + on_up_prev_var <= 1,
            f"transition_constraint_2_{prev_time}_{obj.name}",
        )

    model.add_constraint(entered_up_var <= 1 - on_up_prev_var, f"entered_up_evol_1_{time}_{obj.name}")
    model.add_constraint(entered_up_var <= on_up_var, f"entered_up_evol_2_{time}_{obj.name}")
    model.add_constraint(
        entered_up_var >= on_up_var - on_up_prev_var,
        f"entered_up_evol_3_{time}_{obj.name}",
    )

    model.add_constraint(
        entered_down_var <= 1 - on_down_prev_var,
        f"entered_down_evol_1_{time}_{obj.name}",
    )
    model.add_constraint(entered_down_var <= on_down_var, f"entered_up_evol_2_{time}_{obj.name}")
    model.add_constraint(
        entered_down_var >= on_down_var - on_down_prev_var,
        f"entered_up_evol_3_{time}_{obj.name}",
    )

    model.add_constraint(
        aux_up_grad_var <= max_power * on_up_prev_var,
        f"tilde_U_evol_1_{time}_{obj.name}",
    )
    model.add_constraint(
        aux_up_grad_var >= min_power * on_up_prev_var,
        f"tilde_U_evol_2_{time}_{obj.name}",
    )
    model.add_constraint(
        aux_up_grad_var <= power_level_var - power_level_prev_var - min_power * (1 - on_up_prev_var),
        f"tilde_U_evol_3_{time}_{obj.name}",
    )
    model.add_constraint(
        aux_up_grad_var >= power_level_var - power_level_prev_var - max_power * (1 - on_up_prev_var),
        f"tilde_U_evol_4_{time}_{obj.name}",
    )

    model.add_constraint(
        aux_down_grad_var <= max_power * on_down_prev_var,
        f"tilde_D_evol_1_{time}_{obj.name}",
    )
    model.add_constraint(
        aux_down_grad_var >= min_power * on_down_prev_var,
        f"tilde_D_evol_2_{time}_{obj.name}",
    )
    model.add_constraint(
        aux_down_grad_var <= power_level_var - power_level_prev_var - min_power * (1 - on_down_prev_var),
        f"tilde_D_evol_3_{time}_{obj.name}",
    )
    model.add_constraint(
        aux_down_grad_var >= power_level_var - power_level_prev_var - max_power * (1 - on_down_prev_var),
        f"tilde_D_evol_4_{time}_{obj.name}",
    )

    model.add_constraint(up_grad_var <= max_power * on_up_var, f"U_evol_1_{time}_{obj.name}")
    model.add_constraint(up_grad_var >= min_power * on_up_var, f"U_evol_2_{time}_{obj.name}")
    model.add_constraint(
        up_grad_var <= aux_up_grad_var - min_power * (1 - on_up_var),
        f"U_evol_3_{time}_{obj.name}",
    )
    model.add_constraint(
        up_grad_var >= aux_up_grad_var - max_power * (1 - on_up_var),
        f"U_evol_4_{time}_{obj.name}",
    )

    model.add_constraint(down_grad_var <= max_power * on_down_var, f"D_evol_1_{time}_{obj.name}")
    model.add_constraint(down_grad_var >= min_power * on_down_var, f"D_evol_2_{time}_{obj.name}")
    model.add_constraint(
        down_grad_var <= aux_down_grad_var - min_power * (1 - on_down_var),
        f"D_evol_3_{time}_{obj.name}",
    )
    model.add_constraint(
        down_grad_var >= aux_down_grad_var - max_power * (1 - on_down_var),
        f"D_evol_4_{time}_{obj.name}",
    )

    model.add_constraint(
        off_var + on_up_var + on_down_var + on_flat_var + start_var == 1,
        f"mutual_exclusion_{time}_{obj.name}",
    )

    model.add_constraint(on_up_prev_var + on_down_var <= 1, f"transition_constraint_1_{time}_{obj.name}")
    model.add_constraint(on_down_prev_var + on_up_var <= 1, f"transition_constraint_2_{time}_{obj.name}")
    model.add_constraint(on_up_prev_var + start_var <= 1, f"transition_constraint_3_{time}_{obj.name}")
    model.add_constraint(on_down_prev_var + start_var <= 1, f"transition_constraint_4_{time}_{obj.name}")
    model.add_constraint(on_flat_prev_var + start_var <= 1, f"transition_constraint_5_{time}_{obj.name}")
    model.add_constraint(off_var + start_prev_var <= 1, f"transition_constraint_6_{time}_{obj.name}")
    model.add_constraint(off_prev_var + on_flat_var <= 1, f"transition_constraint_7_{time}_{obj.name}")
    model.add_constraint(off_prev_var + on_down_var <= 1, f"transition_constraint_8_{time}_{obj.name}")
    model.add_constraint(off_prev_var + on_up_var <= 1, f"transition_constraint_9_{time}_{obj.name}")

    eviction_time = time - (obj._T_start - 1) * parameters.timestep
    turned_on_eviction_var = model.get_variable(f"t_on_{obj.name}_{eviction_time}")
    model.add_constraint(
        turned_on_eviction_var + start_var <= 1,
        f"eviction_constraint_{time}_{obj.name}",
    )

    # Minimum time constraints
    if obj._T_on >= 2:
        for s in range(1, obj._T_on):
            local_time = time - (s + obj._T_start) * parameters.timestep
            turned_on_local_var = obj.turned_on.get_value(local_time)
            model.add_constraint(
                turned_on_local_var <= on_up_var + on_down_var + on_flat_var,
                f"minimum_time_on_{obj.name}_{local_time}_{time}",
            )
            if time == parameters.start_date:
                local_time = time - (s + obj._T_start + 1) * parameters.timestep
                turned_on_local_var = obj.turned_on.get_value(local_time)
                model.add_constraint(
                    turned_on_local_var <= on_up_prev_var + on_down_prev_var + on_flat_prev_var,
                    f"minimum_time_on_{obj.name}_{local_time}_{prev_time}",
                )

    if obj._T_off >= 2:
        for s in range(1, obj._T_off):
            local_time = time - (s + obj._T_stop) * parameters.timestep
            turned_off_local_var = obj.turned_off.get_value(local_time)
            model.add_constraint(
                turned_off_local_var <= off_var,
                f"minimum_time_off_{obj.name}_{local_time}_{time}",
            )

    if obj._T_stable >= 2:
        for s in range(1, obj._T_stable - 1):
            local_time = time - s * parameters.timestep
            stable_local_var = obj.stable_var.get_value(local_time)
            model.add_constraint(
                stable_local_var <= on_flat_var,
                f"minimum_time_stable_{obj.name}_{local_time}_{time}",
            )

            if time == parameters.start_date:
                local_time = time - (s + 1) * parameters.timestep
                stable_local_var = obj.stable_var.get_value(local_time)
                model.add_constraint(
                    stable_local_var <= on_flat_prev_var,
                    f"minimum_time_stable_{obj.name}_{local_time}_{prev_time}",
                )

    if obj._T_start >= 2:
        for s in range(1, obj._T_stop - 1):
            local_time = time - s * parameters.timestep
            turned_on_local_var = obj.turned_on.get_value(local_time)
            model.add_constraint(
                turned_on_local_var <= start_var,
                f"startup_ramp_{obj.name}_{local_time}_{time}",
            )

    model.add_constraint(
        power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
        <= max_power + parameters.allowed_round_off_error,
        f"up_fillup_1_{time}_{obj.name}",
    )
    model.add_constraint(
        power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
        >= max_power - parameters.allowed_round_off_error,
        f"up_fillup_2_{time}_{obj.name}",
    )

    model.add_constraint(
        power_level_var
        - reserves_down_var
        - automated_reserves_down_var
        - unprovided_reserves_down_var
        + relaxed_reserves_var
        <= min_power + parameters.allowed_round_off_error,
        f"down_fillup_1_{time}_{obj.name}",
    )
    model.add_constraint(
        power_level_var
        - reserves_down_var
        - automated_reserves_down_var
        - unprovided_reserves_down_var
        + relaxed_reserves_var
        >= min_power - parameters.allowed_round_off_error,
        f"down_fillup_2_{time}_{obj.name}",
    )

    model.add_constraint(
        relaxed_reserves_var <= min_power * (1 - on_up_var - on_flat_var - on_down_var),
        f"relaxed_reserves_{time}_{obj.name}",
    )

    model.add_constraint(
        automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var),
        f"automated_reserves_up_max_{time}_{obj.name}",
    )
    model.add_constraint(
        automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var),
        f"automated_reserves_down_max_{time}_{obj.name}",
    )

    model.add_constraint(
        reserves_up_var <= max_power * (1 - on_up_var - on_down_var - off_var - start_var),
        f"reserves_up_max_{time}_{obj.name}",
    )
    model.add_constraint(
        reserves_down_var <= max_power * (1 - on_up_var - on_down_var - off_var - start_var),
        f"reserves_down_max_{time}_{obj.name}",
    )

    model.add_constraint(
        power_level_var >= min_power * (on_up_var + on_down_var + on_flat_var),
        f"lower_bound_{obj.name}_{time}",
    )

    (
        model.add_constraint(
            power_level_var <= max_power * (on_up_var + on_down_var + on_flat_var) + start_var * q_min
        ),
        f"upper_bound_{obj.name}_{time}",
    )

    if time in obj.optimisation_time_window[:-1]:
        if obj._Delta_Q > 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q * entered_up_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                + q_step * (turned_on_var + start_var),
                f"upward_gradient_{obj.name}_{time}",
            )

            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q * entered_down_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                - obj._Delta_Q_unconstrained * turned_off_var
                + (turned_on_var + start_var) * q_step,
                f"downward_gradient_{obj.name}_{time}",
            )
        elif obj._Delta_Q == 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q_unconstrained * entered_up_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                + q_step * (turned_on_var + start_var),
                f"unconstrained_upward_gradient_{obj.name}_{time}",
            )

            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q_unconstrained * entered_down_prev_var
                + up_grad_prev_var
                + down_grad_prev_var
                - obj._Delta_Q_unconstrained * turned_off_var
                + (start_prev_var + turned_on_var) * q_step,
                f"unconstrained_downward_gradient_{obj.name}_{time}",
            )
