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
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
    extended_start_date: DateTime,
    day_zero: bool,
    **kwargs,
) -> None:
    """Combination 7: T_stop=1, T_start>=1, T_stable>=0

    Args:
        obj: The thermal unit to initialize
        model: The optimization model
        parameters: Portfolio optimization parameters
        extended_start_date: The extended start date for initialization
        day_zero: Whether this is day zero (no historical data)
        **kwargs: Additional arguments including:
            - power_timeseries: Historical power data (required if day_zero=False)
            - initial_times: List of times to initialize
    """
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(obj, model, time)
            initialize_day_zero_on_states(obj, time)

            obj.down_to_stop_grad.set_extended(time, 0)
            obj.on_start_var.set_extended(time, 0)

    else:
        # Non-dayZero case: Initialize based on power history
        power_timeseries = kwargs.get("power_timeseries")
        if not isinstance(power_timeseries, Timeseries):
            raise ValueError("power_timeseries is required in kwargs when day_zero is False")
        if obj.minimum_power is None:
            raise ValueError("minimum_power is required when day_zero is False")

        for time in kwargs.get("initial_times", []):
            power_t = power_timeseries.get_value(time)
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

            # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
            obj.turned_on.set_extended(time, 0)
            obj.turned_off.set_extended(time, 0)
            obj.down_to_stop_grad.set_extended(time, 0)

            # Distinguish between startup and shutdown for intermediate power levels
            if time != extended_start_date:
                prev_time = time - parameters.timestep

                if obj.on_start_var.get_extended_value(time) == 1:
                    if power_timeseries.get_value(prev_time) < power_t:
                        obj.stop_var.set_extended(time, 0)

                    if power_timeseries.get_value(prev_time) > power_t:
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

    prev_time = time - parameters.timestep

    off_var = obj.off_var.get_value(time)
    on_up_var = obj.on_up_var.get_value(time)
    on_down_var = obj.on_down_var.get_value(time)
    start_var = obj.on_start_var.get_value(time)
    stop_var = obj.stop_var.get_value(time)
    turned_on_var = obj.turned_on.get_value(time)
    turned_off_var = obj.turned_off.get_value(time)
    down_to_stop_var = obj.down_to_stop_grad.get_value(time)
    power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")

    off_prev_var = obj.off_var.get_value(prev_time)
    on_up_prev_var = obj.on_up_var.get_value(prev_time)
    on_down_prev_var = obj.on_down_var.get_value(prev_time)
    start_prev_var = obj.on_start_var.get_value(prev_time)
    stop_prev_var = obj.stop_var.get_value(prev_time)
    power_prev_var = model.get_variable(f"{obj.name}_power_level_{prev_time}")

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

    model.add_constraint(turned_on_var <= 1 - off_var)
    model.add_constraint(turned_on_var <= off_prev_var)
    model.add_constraint(turned_on_var >= off_prev_var - off_var)

    model.add_constraint(turned_off_var <= 1 - stop_prev_var)
    model.add_constraint(turned_off_var <= stop_var)
    model.add_constraint(turned_off_var >= stop_var - stop_prev_var)

    model.add_constraint(down_to_stop_var <= stop_var)
    model.add_constraint(down_to_stop_var <= on_down_prev_var)
    model.add_constraint(down_to_stop_var >= stop_var + on_down_prev_var - 1)

    model.add_constraint(off_var + on_up_var + on_down_var + stop_var + start_var == 1)

    model.add_constraint(stop_prev_var + on_up_var <= 1)
    model.add_constraint(stop_prev_var + on_down_var <= 1)

    model.add_constraint(off_prev_var + stop_var <= 1)

    model.add_constraint(on_up_prev_var + off_var <= 1)
    model.add_constraint(on_down_prev_var + off_var <= 1)

    model.add_constraint(on_up_prev_var + start_var <= 1)
    model.add_constraint(on_down_prev_var + start_var <= 1)

    model.add_constraint(start_prev_var + off_var <= 1)
    model.add_constraint(start_prev_var + stop_var <= 1)

    model.add_constraint(stop_prev_var + start_var <= 1)

    model.add_constraint(off_prev_var + on_up_var <= 1)
    model.add_constraint(off_prev_var + on_down_var <= 1)

    start_eviction_time = time - (obj._T_start - 1) * parameters.timestep
    turned_on_start_eviction_var = obj.turned_on.get_value(start_eviction_time)
    model.add_constraint(turned_on_start_eviction_var + start_var <= 1)

    stop_eviction_time = time - (obj._T_stop - 1) * parameters.timestep
    turned_off_stop_eviction_var = obj.turned_off.get_value(stop_eviction_time)
    model.add_constraint(turned_off_stop_eviction_var + stop_var <= 1)

    if obj._T_on >= 2:
        for s in range(1, obj._T_on):
            local_time = time - (s + obj._T_start) * parameters.timestep
            turned_on_local_var = obj.turned_on.get_value(local_time)
            model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

    if obj._T_off >= 2:
        for s in range(1, obj._T_off):
            local_time = time - (s + obj._T_stop) * parameters.timestep
            turned_off_local_var = obj.turned_off.get_value(local_time)
            model.add_constraint(turned_off_local_var <= off_var)

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
        <= q_upper + parameters.allowed_round_off_error
    )
    model.add_constraint(
        power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
        >= q_upper - parameters.allowed_round_off_error
    )

    model.add_constraint(
        power_level_var
        - reserves_down_var
        - automated_reserves_down_var
        - unprovided_reserves_down_var
        + relaxed_reserves_var
        <= q_lower + parameters.allowed_round_off_error
    )
    model.add_constraint(
        power_level_var
        - reserves_down_var
        - automated_reserves_down_var
        - unprovided_reserves_down_var
        + relaxed_reserves_var
        >= q_lower - parameters.allowed_round_off_error
    )

    model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_down_var))

    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var - stop_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var - stop_var))
    model.add_constraint(reserves_up_var <= q_upper * (1 - off_var - start_var - stop_var))
    model.add_constraint(reserves_down_var <= q_upper * (1 - off_var - start_var - stop_var))

    model.add_constraint(
        power_level_var >= q_lower * (on_up_var + on_down_var) + turned_off_var * (q_min - q_step_down)
    )

    model.add_constraint(
        power_level_var
        <= q_upper * (on_up_var + on_down_var) + (stop_var + start_var) * q_min - turned_off_var * q_step_down
    )

    if time in obj.optimisation_time_window[:-1]:
        if obj._Delta_Q > 0:
            model.add_constraint(
                power_level_var - power_prev_var
                <= obj._Delta_Q * on_up_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + (turned_on_var + start_prev_var) * q_step_up
            )

            model.add_constraint(
                power_level_var - power_prev_var
                >= -obj._Delta_Q * on_down_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + down_to_stop_var * obj._Delta_Q
                + (turned_on_var + start_prev_var) * q_step_up
            )
        elif obj._Delta_Q == 0:
            model.add_constraint(
                power_level_var - power_prev_var
                <= obj._Delta_Q_unconstrained * on_up_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + (turned_on_var + start_prev_var) * q_step_up
            )

            model.add_constraint(
                power_level_var - power_prev_var
                >= -obj._Delta_Q_unconstrained * on_down_prev_var
                - (turned_off_var + stop_prev_var) * q_step_down
                + down_to_stop_var * obj._Delta_Q_unconstrained
                + (turned_on_var + start_prev_var) * q_step_up
            )
