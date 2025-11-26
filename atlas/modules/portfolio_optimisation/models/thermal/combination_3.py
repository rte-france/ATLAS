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
    parameters: PortfolioOptimisationParameters,
    extended_start_date: DateTime,
    day_zero: bool,
    **kwargs,
) -> None:
    """Combination 3: T_stop=0, T_start=0, T_stable>=1"""
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(obj, time)
            initialize_day_zero_gradient_vars(obj, time)

        for time in kwargs.get("stable_initial_times", []):
            initialize_day_zero_stable_vars(obj, time)

        power_ts = kwargs.get("power_ts")
        if isinstance(power_ts, Timeseries):
            initialize_gradient_initial_conditions(obj, parameters)

    else:
        power_ts = kwargs.get("power_ts")
        if not isinstance(power_ts, Timeseries):
            raise ValueError("power_ts is required in kwargs when day_zero is False")
        if obj.minimum_power is None:
            raise ValueError("minimum_power is required when day_zero is False")

        for time in kwargs.get("initial_times", []):
            if time in power_ts:
                power_t = power_ts.get_value(time)
                obj.power_level_var.set_extended(time, power_t)

                if power_t > 0:
                    obj.off_var.set_extended(time, 0)
                else:
                    obj.power_level_var.set_extended(time, 0)
                    obj.off_var.set_extended(time, 1)
            else:
                obj.off_var.set_extended(time, 1)
                obj.power_level_var.set_extended(time, 0)

            obj.turned_off.set_extended(time, 0)
            obj.turned_on.set_extended(time, 0)

            if time != extended_start_date:
                prev_time = time - parameters.timestep

                if obj.off_var.get_extended_value(time) - obj.off_var.get_extended_value(prev_time) == 1:
                    obj.turned_off.set_extended(time, 1)

                # Detect turn on: was OFF -> now ON
                elif obj.off_var.get_extended_value(time) - obj.off_var.get_extended_value(prev_time) == -1:
                    obj.turned_on.set_extended(time, 1)

        for time in kwargs.get("stable_initial_times", []):
            if obj.off_var.get_extended_value(time) == 0:
                next_time = time + parameters.timestep
                current_power = obj.power_level_var.get_extended_value(time)
                next_power = obj.power_level_var.get_extended_value(next_time)

                if current_power < next_power:
                    obj.on_up_var.set_extended(time, 1)
                    obj.on_down_var.set_extended(time, 0)
                    obj.on_flat_var.set_extended(time, 0)

                elif current_power > next_power:
                    obj.on_up_var.set_extended(time, 0)
                    obj.on_down_var.set_extended(time, 1)
                    obj.on_flat_var.set_extended(time, 0)

                else:
                    # Power is stable
                    obj.on_up_var.set_extended(time, 0)
                    obj.on_down_var.set_extended(time, 0)
                    obj.on_flat_var.set_extended(time, 1)
            else:
                obj.on_up_var.set_extended(time, 0)
                obj.on_down_var.set_extended(time, 0)
                obj.on_flat_var.set_extended(time, 0)

            obj.stable_var.set_extended(time, 0)
            obj.entered_up_var.set_extended(time, 0)
            obj.entered_down_var.set_extended(time, 0)

            # Detect state transitions for non-initial times
            if time != extended_start_date:
                prev_time = time - parameters.timestep
                if obj.on_flat_var.get_extended_value(time) - obj.on_flat_var.get_extended_value(prev_time) == 1:
                    obj.stable_var.set_extended(time, 1)

                if obj.on_up_var.get_extended_value(time) - obj.on_up_var.get_extended_value(prev_time) == 1:
                    obj.entered_up_var.set_extended(time, 1)

                if obj.on_down_var.get_extended_value(time) - obj.on_down_var.get_extended_value(prev_time) == 1:
                    obj.entered_down_var.set_extended(time, 1)

        initialize_gradient_initial_conditions(obj, parameters)


def add_constraints(
    obj: ThermalPO,
    time: DateTime,
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
) -> None:
    """Add constraints for Combination 3: T_start = 0, T_stop = T_stable >= 1"""

    if obj.minimum_power is None or obj.maximum_power is None:
        raise ValueError("minimum_power and maximum_power cannot be None")

    prev_time = time - parameters.timestep

    # Get variables
    off_var = obj.off_var.get_value(time)
    on_up_var = obj.on_up_var.get_value(time)
    on_down_var = obj.on_down_var.get_value(time)
    on_flat_var = obj.on_flat_var.get_value(time)
    turned_on_var = obj.turned_on.get_value(time)
    turned_off_var = obj.turned_off.get_value(time)
    stable_var = obj.stable_var.get_value(time)
    entered_up_var = obj.entered_up_var.get_value(time)
    entered_down_var = obj.entered_down_var.get_value(time)
    power_level_var = obj.power_level_var.get_value(time)

    # Gradient auxiliary variables
    up_grad_var = obj.up_grad_var.get_value(time)
    aux_up_grad_var = obj.aux_up_grad_var.get_value(time)
    down_grad_var = obj.down_grad_var.get_value(time)
    aux_down_grad_var = obj.aux_down_grad_var.get_value(time)

    # Previous time variables
    off_prev_var = obj.off_var.get_value(prev_time)
    on_up_prev_var = obj.on_up_var.get_value(prev_time)
    on_down_prev_var = obj.on_down_var.get_value(prev_time)
    on_flat_prev_var = obj.on_flat_var.get_value(prev_time)
    entered_up_prev_var = obj.entered_up_var.get_value(prev_time)
    entered_down_prev_var = obj.entered_down_var.get_value(prev_time)
    stable_prev_var = obj.stable_var.get_value(prev_time)

    power_level_prev_var = obj.power_level_var.get_value(prev_time)
    on_up_prev_2_var = obj.on_up_var.get_value(prev_time - parameters.timestep)
    on_down_prev_2_var = obj.on_down_var.get_value(prev_time - parameters.timestep)
    on_flat_prev_2_var = obj.on_flat_var.get_value(prev_time - parameters.timestep)

    # Reserve variables
    reserves_up_var = model.get_variable(f"reserves_up_{obj.name}_{time}")
    reserves_down_var = model.get_variable(f"reserves_down_{obj.name}_{time}")
    automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{obj.name}_{time}")
    automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{obj.name}_{time}")
    unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{obj.name}_{time}")
    unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{obj.name}_{time}")
    relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{obj.name}_{time}")

    max_power = obj.maximum_power.get_value(time)
    min_power = -max_power
    maximum_automated = get_maximum_automated(obj)

    model.add_constraint(turned_on_var <= 1 - off_var, f"t_on_evol_1_{time}_{obj.name}")
    model.add_constraint(turned_on_var <= off_prev_var, f"t_on_evol_2_{time}_{obj.name}")
    (
        model.add_constraint(turned_on_var >= off_prev_var - off_var),
        f"t_on_evol_3_{time}_{obj.name}",
    )

    model.add_constraint(turned_off_var <= 1 - off_prev_var, f"t_off_evol_1_{time}_{obj.name}")
    model.add_constraint(turned_off_var <= off_var, f"t_off_evol_2_{time}_{obj.name}")
    model.add_constraint(turned_off_var >= off_var - off_prev_var, f"t_off_evol_3_{time}_{obj.name}")

    model.add_constraint(stable_var <= 1 - on_flat_prev_var, f"stable_evol_1_{time}_{obj.name}")
    model.add_constraint(stable_var <= on_flat_var, f"stable_evol_2_{time}_{obj.name}")
    model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var, f"stable_evol_3_{time}_{obj.name}")

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
    model.add_constraint(entered_down_var <= on_down_var, f"entered_down_evol_2_{time}_{obj.name}")
    model.add_constraint(
        entered_down_var >= on_down_var - on_down_prev_var,
        f"entered_down_evol_3_{time}_{obj.name}",
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
        off_var + on_up_var + on_down_var + on_flat_var == 1,
        f"mutual_exclusion_{time}_{obj.name}",
    )

    model.add_constraint(on_up_prev_var + on_down_var <= 1, f"transition_constraint_1_{time}_{obj.name}")
    model.add_constraint(on_down_prev_var + on_up_var <= 1, f"transition_constraint_2_{time}_{obj.name}")

    if time == parameters.start_date:
        (
            model.add_constraint(off_prev_var + on_up_prev_var + on_down_prev_var + on_flat_prev_var == 1),
            f"mutual_exclusion_{time}_{obj.name}",
        )
        model.add_constraint(
            on_up_prev_2_var + on_down_prev_var <= 1,
            f"transition_constraint_1_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            on_down_prev_2_var + on_up_prev_var <= 1,
            f"transition_constraint_2_{prev_time}_{obj.name}",
        )

        model.add_constraint(
            stable_prev_var <= 1 - on_flat_prev_2_var,
            f"stable_evol_1_{prev_time}_{obj.name}",
        )
        model.add_constraint(stable_prev_var <= on_flat_prev_var, f"stable_evol_2_{prev_time}_{obj.name}")
        model.add_constraint(
            stable_prev_var >= on_flat_prev_var - on_flat_prev_2_var,
            f"stable_evol_3_{prev_time}_{obj.name}",
        )

        model.add_constraint(
            entered_up_prev_var <= 1 - on_up_prev_2_var,
            f"entered_up_evol_1_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            entered_up_prev_var <= on_up_prev_var,
            f"entered_up_evol_2_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            entered_up_prev_var >= on_up_prev_var - on_up_prev_2_var,
            f"entered_up_evol_3_{prev_time}_{obj.name}",
        )

        model.add_constraint(
            entered_down_prev_var <= 1 - on_down_prev_2_var,
            f"entered_down_evol_1_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            entered_down_prev_var <= on_down_prev_var,
            f"entered_down_evol_2_{prev_time}_{obj.name}",
        )
        model.add_constraint(
            entered_down_prev_var >= on_down_prev_var - on_down_prev_2_var,
            f"entered_down_evol_3_{prev_time}_{obj.name}",
        )

    if obj._T_on >= 2:
        for s in range(1, obj._T_on):
            local_time = time - s * parameters.timestep
            turned_on_local_var = obj.turned_on.get_value(local_time)
            model.add_constraint(
                turned_on_local_var <= on_up_var + on_down_var + on_flat_var,
                f"minimum_time_on_{obj.name}_{local_time}_{time}",
            )

    if obj._T_off >= 2:
        for s in range(1, obj._T_off):
            local_time = time - s * parameters.timestep
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
        automated_reserves_up_var <= maximum_automated * (1 - off_var),
        f"automated_reserves_up_max_{time}_{obj.name}",
    )
    model.add_constraint(
        automated_reserves_down_var <= maximum_automated * (1 - off_var),
        f"automated_reserves_down_max_{time}_{obj.name}",
    )

    model.add_constraint(
        reserves_up_var <= max_power * (1 - off_var - on_up_var - on_down_var),
        f"reserves_up_max_{time}_{obj.name}",
    )
    model.add_constraint(
        reserves_down_var <= max_power * (1 - off_var - on_up_var - on_down_var),
        f"reserves_down_max_{time}_{obj.name}",
    )

    model.add_constraint(
        power_level_var >= min_power * (on_up_var + on_down_var + on_flat_var),
        f"lower_bound_{obj.name}_{time}",
    )
    model.add_constraint(
        power_level_var <= max_power * (on_up_var + on_down_var + on_flat_var),
        f"upper_bound_{obj.name}_{time}",
    )

    if time in obj.optimisation_time_window[:-2]:
        if obj._Delta_Q > 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q * entered_up_var
                + up_grad_var
                + down_grad_var
                + obj._Delta_Q_unconstrained * turned_on_var,
                f"upward_gradient_{obj.name}_{time}",
            )

            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q * entered_down_var
                + up_grad_var
                + down_grad_var
                - obj._Delta_Q_unconstrained * turned_off_var,
                f"downward_gradient_{obj.name}_{time}",
            )
        elif obj._Delta_Q == 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q_unconstrained * entered_up_var
                + up_grad_var
                + down_grad_var
                + obj._Delta_Q_unconstrained * turned_on_var,
                f"unconstrained_upward_gradient_{obj.name}_{time}",
            )
            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q_unconstrained * entered_down_var
                + up_grad_var
                + down_grad_var
                - obj._Delta_Q_unconstrained * turned_off_var,
                f"unconstrained_downward_gradient_{obj.name}_{time}",
            )
