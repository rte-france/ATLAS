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
    """Combination 2: T_stop>=1, T_start=0, T_stable=0"""
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(obj, model, time)
            initialize_day_zero_on_states(obj, model, time)

            obj.stop_var.set_extended(time, 0)
            obj.down_to_stop_grad.set_extended(time, 0)
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

            # Get variables

            # Set state variables based on power level relative to minimum power
            if power_t >= min_power:
                # Unit is ON and above minimum power
                obj.off_var.set_extended(time, 0)
                obj.stop_var.set_extended(time, 0)
                obj.on_up_var.set_extended(time, 1)
                obj.on_down_var.set_extended(time, 1)

            elif power_t > 0:
                obj.off_var.set_extended(time, 0)
                obj.stop_var.set_extended(time, 1)
                obj.on_up_var.set_extended(time, 0)
                obj.on_down_var.set_extended(time, 0)

            else:
                obj.off_var.set_extended(time, 1)
                obj.stop_var.set_extended(time, 0)
                obj.on_up_var.set_extended(time, 0)
                obj.on_down_var.set_extended(time, 0)

            obj.turned_on_var.set_extended(time, 0)
            obj.turned_off_var.set_extended(time, 0)
            obj.down_to_stop_grad.set_extended(time, 0)

            if time != extended_start_date:
                prev_time = time - parameters.timestep

                if obj.stop_var.get_extended_value(time) - obj.stop_var.get_extended_value(prev_time) == 1:
                    obj.turned_off.set_extended(time, 1)

                elif obj.off_var.get_extended_value(time) - obj.off_var.get_extended_value(prev_time) == -1:
                    obj.turned_on.set_extended(time, 1)

                elif obj.stop_var.get_extended_value(time) - obj.on_down_var.get_extended_value(prev_time) == 0:
                    obj.down_to_stop_grad.set_extended(time, 1)


def add_constraints(
    obj: ThermalPO, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
) -> None:
    """Add constraints for Combination 2: T_stop >= 1, T_stable = T_start = 0"""

    if obj.minimum_power is None or obj.maximum_power is None:
        raise ValueError("minimum_power and maximum_power cannot be None")

    prev_time = time - parameters.timestep

    # Get variables
    power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")
    power_level_prev_var = model.get_variable(f"{obj.name}_power_level_{prev_time}")

    # Reserve variables
    reserves_up_var = model.get_variable(f"reserves_up_{obj.name}_{time}")
    reserves_down_var = model.get_variable(f"reserves_down_{obj.name}_{time}")
    automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{obj.name}_{time}")
    automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{obj.name}_{time}")
    unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{obj.name}_{time}")
    unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{obj.name}_{time}")
    relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{obj.name}_{time}")

    # Power bounds and parameters
    max_power = obj.maximum_power.get_value(time)
    min_power = obj.minimum_power.get_value(time)
    maximum_automated = get_maximum_automated(obj)

    # Shutdown gradient parameters
    q_min = obj.minimum_power.max()  # Get the minimum power without reserve requirements
    q_step = q_min / obj._T_stop

    model.add_constraint(obj.turned_on.get_value(time) <= 1 - obj.off_var.get_value(time))
    model.add_constraint(obj.turned_on.get_value(time) <= obj.off_var.get_value(prev_time))
    model.add_constraint(
        obj.turned_on.get_value(time) >= obj.off_var.get_value(prev_time) - obj.off_var.get_value(time)
    )

    model.add_constraint(obj.turned_off.get_value(time) <= 1 - obj.stop_var.get_value(prev_time))
    model.add_constraint(obj.turned_off.get_value(time) <= obj.stop_var.get_value(time))
    model.add_constraint(
        obj.turned_off.get_value(time) >= obj.stop_var.get_value(time) - obj.stop_var.get_value(prev_time)
    )

    model.add_constraint(obj.down_to_stop_grad.get_value(time) <= 1 - obj.on_down_var.get_value(prev_time))
    model.add_constraint(obj.down_to_stop_grad.get_value(time) <= obj.on_down_var.get_value(time))
    model.add_constraint(
        obj.down_to_stop_grad.get_value(time) >= obj.on_down_var.get_value(time) - obj.on_down_var.get_value(prev_time)
    )

    model.add_constraint(
        obj.off_var.get_value(time)
        + obj.on_up_var.get_value(time)
        + obj.on_down_var.get_value(time)
        + obj.stop_var.get_value(time)
        == 1
    )

    model.add_constraint(obj.stop_var.get_value(prev_time) + obj.on_up_var.get_value(time) <= 1)
    model.add_constraint(obj.stop_var.get_value(prev_time) + obj.on_down_var.get_value(time) <= 1)
    model.add_constraint(obj.off_var.get_value(prev_time) + obj.stop_var.get_value(time) <= 1)
    model.add_constraint(obj.on_up_var.get_value(prev_time) + obj.off_var.get_value(time) <= 1)
    model.add_constraint(obj.on_down_var.get_value(prev_time) + obj.off_var.get_value(time) <= 1)

    eviction_time = time - (obj._T_stop - 1) * parameters.timestep
    turned_off_eviction_var = model.get_variable(f"t_off_of_{obj.name}_{eviction_time}")
    model.add_constraint(turned_off_eviction_var + obj.stop_var.get_value(time) <= 1)

    if obj._T_on >= 2:
        for s in range(1, obj._T_on):
            local_time = time - s * parameters.timestep
            turned_on_local_var = model.get_variable(f"t_on_of_{obj.name}_{local_time}")
            model.add_constraint(turned_on_local_var <= obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time))

    if obj._T_off >= 2:
        for s in range(1, obj._T_off):
            local_time = time - (s + obj._T_stop) * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{obj.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= obj.off_var.get_value(time))

    if obj._T_stop >= 2:
        for s in range(1, obj._T_stop - 1):
            local_time = time - s * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{obj.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= obj.stop_var.get_value(time))

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

    model.add_constraint(
        relaxed_reserves_var <= min_power * (1 - obj.on_up_var.get_value(time) - obj.on_down_var.get_value(time))
    )

    model.add_constraint(
        automated_reserves_up_var
        <= maximum_automated * (1 - obj.off_var.get_value(time) - obj.stop_var.get_value(time))
    )
    model.add_constraint(
        automated_reserves_down_var
        <= maximum_automated * (1 - obj.off_var.get_value(time) - obj.stop_var.get_value(time))
    )
    model.add_constraint(
        reserves_up_var <= max_power * (1 - obj.off_var.get_value(time) - obj.stop_var.get_value(time))
    )
    model.add_constraint(
        reserves_down_var <= max_power * (1 - obj.off_var.get_value(time) - obj.stop_var.get_value(time))
    )

    model.add_constraint(
        power_level_var
        >= min_power * (obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time))
        + obj.turned_off.get_value(time) * (q_min - q_step)
    )
    model.add_constraint(
        power_level_var
        <= max_power * (obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time))
        + obj.stop_var.get_value(time) * q_min
        - obj.turned_off.get_value(time) * q_step
    )

    if time in obj.optimisation_time_window[:-1]:
        if obj._Delta_Q > 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q * obj.on_up_var.get_value(prev_time)
                - obj.turned_off.get_value(time) * q_step
                - obj.stop_var.get_value(prev_time) * q_step
                + obj._Delta_Q_unconstrained * obj.turned_on.get_value(time)
            )

            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q * obj.on_down_var.get_value(prev_time)
                - obj.turned_off.get_value(time) * q_step
                - obj.stop_var.get_value(prev_time) * q_step
                + obj.down_to_stop_grad.get_value(time) * obj._Delta_Q
            )
        elif obj._Delta_Q == 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q_unconstrained * obj.on_up_var.get_value(prev_time)
                - obj.turned_off.get_value(time) * q_step
                - obj.stop_var.get_value(prev_time) * q_step
                + obj._Delta_Q_unconstrained * obj.turned_on.get_value(time)
            )
            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q_unconstrained * obj.on_down_var.get_value(prev_time)
                - obj.turned_off.get_value(time) * q_step
                - obj.stop_var.get_value(prev_time) * q_step
                + obj._Delta_Q_unconstrained * obj.down_to_stop_grad.get_value(time)
            )
