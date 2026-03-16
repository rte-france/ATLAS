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
    initialize_day_zero_on_states,
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
    """
    Combination 7: T_stop=1, T_start>=1, T_stable>=0

    :param obj: The thermal unit to initialize
    :type obj: ThermalPO
    :param parameters: Portfolio optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :param extended_start_date: The extended start date for initialization
    :type extended_start_date: DateTime
    :param day_zero: Whether this is day zero (no historical data)
    :type day_zero: bool
    :param kwargs: Additional arguments including power_ts (historical power data) and initial_times (list of times to initialize)
    :type kwargs: dict
    """
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(obj, time)
            initialize_day_zero_on_states(obj, time)

            obj.down_to_stop_grad.set_extended(time, 0)
            obj.on_start_var.set_extended(time, 0)
            obj.stop_var.set_extended(time, 0)

    else:
        # Non-dayZero case: Initialize based on power history
        power_ts = kwargs.get("power_ts")
        if not isinstance(power_ts, Timeseries):
            raise ValueError("power_ts is required in kwargs when day_zero is False")
        if obj.minimum_power is None:
            raise ValueError("minimum_power is required when day_zero is False")

        for time in kwargs.get("initial_times", []):
            if time in power_ts:
                power_t = power_ts.get_value(time)
                obj.power_level_var.set_extended(time, power_t)
                min_power = obj.minimum_power.get_value(time)

                # Set state variables based on power level relative to minimum power
                if power_t >= min_power:
                    # Unit is ON and above minimum power (normal operation)
                    obj.off_var.set_extended(time, 0)
                    obj.stop_var.set_extended(time, 0)
                    obj.on_start_var.set_extended(time, 0)
                    obj.on_down_var.set_extended(time, 1)
                    obj.on_up_var.set_extended(time, 1)

                elif power_t > 0:
                    obj.off_var.set_extended(time, 0)
                    obj.stop_var.set_extended(time, 1)
                    obj.on_start_var.set_extended(time, 1)
                    obj.on_down_var.set_extended(time, 0)
                    obj.on_up_var.set_extended(time, 0)
                else:
                    # Unit is completely OFF
                    obj.off_var.set_extended(time, 1)
                    obj.stop_var.set_extended(time, 0)
                    obj.on_start_var.set_extended(time, 0)
                    obj.on_down_var.set_extended(time, 0)
                    obj.on_up_var.set_extended(time, 0)
            else:
                obj.power_level_var.set_extended(time, 0)
                obj.off_var.set_extended(time, 1)
                obj.stop_var.set_extended(time, 0)
                obj.on_start_var.set_extended(time, 0)
                obj.on_down_var.set_extended(time, 0)
                obj.on_up_var.set_extended(time, 0)

            obj.turned_on.set_extended(time, 0)
            obj.turned_off.set_extended(time, 0)
            obj.down_to_stop_grad.set_extended(time, 0)

            # Distinguish between startup and shutdown for intermediate power levels
            if time != extended_start_date:
                prev_time = time - parameters.date.timestep

                if obj.on_start_var.get_extended_value(time) == 1:
                    if power_ts.get_value(prev_time) < power_t:
                        obj.stop_var.set_extended(time, 0)

                    if power_ts.get_value(prev_time) > power_t:
                        obj.stop_var.set_extended(time, 1)
                        obj.on_start_var.set_extended(time, 0)

                if obj.stop_var.get_extended_value(time) - obj.stop_var.get_extended_value(prev_time) == 1:
                    obj.turned_off.set_extended(time, 1)

                if obj.on_start_var.get_extended_value(time) - obj.on_start_var.get_extended_value(prev_time) == 1:
                    obj.turned_on.set_extended(time, 1)

                if obj.stop_var.get_extended_value(time) - obj.on_down_var.get_extended_value(prev_time) == 0:
                    obj.down_to_stop_grad.set_extended(time, 1)


def add_constraints(
    obj: ThermalPO, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
) -> None:
    """Add constraints for Combination 7:  T_stop=1, T_start>=1, T_stable>=0"""
    if obj.minimum_power is None or obj.maximum_power is None:
        raise ValueError("minimum_power and maximum_power cannot be None")

    prev_time = time - parameters.date.timestep

    off_var = obj.off_var.get_value(time)
    on_up_var = obj.on_up_var.get_value(time)
    on_down_var = obj.on_down_var.get_value(time)
    start_var = obj.on_start_var.get_value(time)
    stop_var = obj.stop_var.get_value(time)
    turned_on_var = obj.turned_on.get_value(time)
    turned_off_var = obj.turned_off.get_value(time)
    down_to_stop_var = obj.down_to_stop_grad.get_value(time)
    power_level_var = obj.power_level_var.get_value(time)

    off_prev_var = obj.off_var.get_value(prev_time)
    on_up_prev_var = obj.on_up_var.get_value(prev_time)
    on_down_prev_var = obj.on_down_var.get_value(prev_time)
    start_prev_var = obj.on_start_var.get_value(prev_time)
    stop_prev_var = obj.stop_var.get_value(prev_time)
    power_prev_var = obj.power_level_var.get_value(prev_time)

    reserves_up_var = model.get_variable(f"reserves_up_{obj.name}_{time}")
    reserves_down_var = model.get_variable(f"reserves_down_{obj.name}_{time}")
    automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{obj.name}_{time}")
    automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{obj.name}_{time}")
    unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{obj.name}_{time}")
    unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{obj.name}_{time}")
    relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{obj.name}_{time}")

    q_upper = obj.maximum_power.get_value(time)
    q_lower = obj.minimum_power.get_value(time)
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

    model.add_constraint(down_to_stop_var <= stop_var, f"down_to_stop_evol_1_{time}_{obj.name}")
    model.add_constraint(down_to_stop_var <= on_down_prev_var, f"down_to_stop_evol_2_{time}_{obj.name}")
    model.add_constraint(down_to_stop_var >= stop_var + on_down_prev_var - 1, f"down_to_stop_evol_3_{time}_{obj.name}")

    model.add_constraint(
        off_var + on_up_var + on_down_var + stop_var + start_var == 1, f"mutual_exclusion_{time}_{obj.name}"
    )

    model.add_constraint(stop_prev_var + on_up_var <= 1, f"transition_constraint_1_{time}_{obj.name}")
    model.add_constraint(stop_prev_var + on_down_var <= 1, f"transition_constraint_2_{time}_{obj.name}")
    model.add_constraint(off_prev_var + stop_var <= 1, f"transition_constraint_3_{time}_{obj.name}")
    model.add_constraint(on_up_prev_var + off_var <= 1, f"transition_constraint_4_{time}_{obj.name}")
    model.add_constraint(on_down_prev_var + off_var <= 1, f"transition_constraint_5_{time}_{obj.name}")
    model.add_constraint(on_up_prev_var + start_var <= 1, f"transition_constraint_6_{time}_{obj.name}")
    model.add_constraint(on_down_prev_var + start_var <= 1, f"transition_constraint_7_{time}_{obj.name}")
    model.add_constraint(start_prev_var + off_var <= 1, f"transition_constraint_8_{time}_{obj.name}")
    model.add_constraint(start_prev_var + stop_var <= 1, f"transition_constraint_9_{time}_{obj.name}")
    model.add_constraint(stop_prev_var + start_var <= 1, f"transition_constraint_10_{time}_{obj.name}")
    model.add_constraint(off_prev_var + on_up_var <= 1, f"transition_constraint_11_{time}_{obj.name}")
    model.add_constraint(off_prev_var + on_down_var <= 1, f"transition_constraint_12_{time}_{obj.name}")

    start_eviction_time = time - (obj._T_start - 1) * parameters.date.timestep
    turned_on_start_eviction_var = obj.turned_on.get_value(start_eviction_time)
    model.add_constraint(turned_on_start_eviction_var + start_var <= 1, f"start_eviction_constraint_{time}_{obj.name}")

    stop_eviction_time = time - (obj._T_stop - 1) * parameters.date.timestep
    turned_off_stop_eviction_var = obj.turned_off.get_value(stop_eviction_time)
    model.add_constraint(turned_off_stop_eviction_var + stop_var <= 1, f"stop_eviction_constraint_{time}_{obj.name}")

    if obj._T_on >= 2:
        for s in range(1, obj._T_on):
            local_time = time - (s + obj._T_start) * parameters.date.timestep
            turned_on_local_var = obj.turned_on.get_value(local_time)
            model.add_constraint(
                turned_on_local_var <= on_up_var + on_down_var,
                f"minimum_time_on_{obj.name}_{local_time}_{time}",
            )

    if obj._T_off >= 2:
        for s in range(1, obj._T_off):
            local_time = time - (s + obj._T_stop) * parameters.date.timestep
            turned_off_local_var = obj.turned_off.get_value(local_time)
            model.add_constraint(
                turned_off_local_var <= off_var,
                f"minimum_time_off_{obj.name}_{local_time}_{time}",
            )

    if obj._T_stop >= 2:
        for s in range(1, obj._T_stop - 1):
            local_time = time - s * parameters.date.timestep
            turned_off_local_var = obj.turned_off.get_value(local_time)
            model.add_constraint(
                turned_off_local_var <= stop_var,
                f"shutdown_ramp_{obj.name}_{local_time}_{time}",
            )

    if obj._T_start >= 2:
        for s in range(1, obj._T_start - 1):
            local_time = time - s * parameters.date.timestep
            turned_on_local_var = obj.turned_on.get_value(local_time)
            model.add_constraint(
                turned_on_local_var <= start_var,
                f"startup_ramp_{obj.name}_{local_time}_{time}",
            )

    model.add_constraint(
        power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
        <= q_upper + parameters.allowed_round_off_error,
        f"up_fillup_1_{time}_{obj.name}",
    )
    model.add_constraint(
        power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
        >= q_upper - parameters.allowed_round_off_error,
        f"up_fillup_2_{time}_{obj.name}",
    )

    model.add_constraint(
        power_level_var
        - reserves_down_var
        - automated_reserves_down_var
        - unprovided_reserves_down_var
        + relaxed_reserves_var
        <= q_lower + parameters.allowed_round_off_error,
        f"down_fillup_1_{time}_{obj.name}",
    )
    model.add_constraint(
        power_level_var
        - reserves_down_var
        - automated_reserves_down_var
        - unprovided_reserves_down_var
        + relaxed_reserves_var
        >= q_lower - parameters.allowed_round_off_error,
        f"down_fillup_2_{time}_{obj.name}",
    )

    model.add_constraint(
        relaxed_reserves_var <= q_lower * (1 - on_up_var - on_down_var),
        f"relaxed_reserves_{time}_{obj.name}",
    )

    model.add_constraint(
        automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var - stop_var),
        f"automated_reserves_up_max_{time}_{obj.name}",
    )
    model.add_constraint(
        automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var - stop_var),
        f"automated_reserves_down_max_{time}_{obj.name}",
    )
    model.add_constraint(
        reserves_up_var <= q_upper * (1 - off_var - start_var - stop_var), f"reserves_up_max_{time}_{obj.name}"
    )
    model.add_constraint(
        reserves_down_var <= q_upper * (1 - off_var - start_var - stop_var), f"reserves_down_max_{time}_{obj.name}"
    )

    model.add_constraint(
        power_level_var >= q_lower * (on_up_var + on_down_var) + turned_off_var * (q_min - q_step_down),
        f"lower_bound_{obj.name}_{time}",
    )

    model.add_constraint(
        power_level_var
        <= q_upper * (on_up_var + on_down_var) + (stop_var + start_var) * q_min - turned_off_var * q_step_down,
        f"upper_bound_{obj.name}_{time}",
    )

    if time in obj.optimisation_time_window[:-2]:
        if obj._Delta_Q > 0:
            model.add_constraint(
                power_level_var - power_prev_var
                <= obj._Delta_Q * on_up_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + (turned_on_var + start_prev_var) * q_step_up,
                f"upward_gradient_{obj.name}_{time}",
            )

            model.add_constraint(
                power_level_var - power_prev_var
                >= -obj._Delta_Q * on_down_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + down_to_stop_var * obj._Delta_Q
                + (turned_on_var + start_prev_var) * q_step_up,
                f"downward_gradient_{obj.name}_{time}",
            )
        elif obj._Delta_Q == 0:
            model.add_constraint(
                power_level_var - power_prev_var
                <= obj._Delta_Q_unconstrained * on_up_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + (turned_on_var + start_prev_var) * q_step_up,
                f"unconstrained_upward_gradient_{obj.name}_{time}",
            )

            model.add_constraint(
                power_level_var - power_prev_var
                >= -obj._Delta_Q_unconstrained * on_down_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + down_to_stop_var * obj._Delta_Q_unconstrained
                + (turned_on_var + start_prev_var) * q_step_up,
                f"unconstrained_downward_gradient_{obj.name}_{time}",
            )
