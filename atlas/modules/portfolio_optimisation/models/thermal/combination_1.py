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
    """Combination 1: T_stop=0, T_start=0, T_stable=0"""
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(obj, model, time)
            initialize_day_zero_on_states(obj, model, time)
    else:
        # Non-dayZero case: Initialize based on power history
        power_timeseries = kwargs.get("power_timeseries")
        if not isinstance(power_timeseries, Timeseries):
            raise ValueError("power_timeseries is required in kwargs when day_zero is False")

        for time in kwargs.get("initial_times", []):
            power_at_time = power_timeseries.get_value(time)
            # Get variables

            # Set state variables based on power level
            if power_at_time > 0:
                # Unit is ON
                obj.off_var.set_extended(time, 0)
                obj.on_up_var.set_extended(time, 1)
                obj.on_down_var.set_extended(time, 0)

            else:
                # Unit is completely OFF
                obj.off_var.set_extended(time, 1)
                obj.on_up_var.set_extended(time, 0)
                obj.on_down_var.set_extended(time, 0)

            obj.turned_off.set_extended(time, 0)
            obj.turned_on.set_extended(time, 0)

            if time != extended_start_date:
                prev_time = time - parameters.timestep

                if obj.off_var.get_extended_value(time) - obj.off_var.get_extended_value(prev_time) == 1:
                    obj.turned_off.set_extended(time, 1)

                elif obj.off_var.get_extended_value(time) - obj.off_var.get_extended_value(prev_time) == -1:
                    obj.turned_on.set_extended(time, 1)


def add_constraints(
    obj: ThermalPO,
    time: DateTime,
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
) -> None:
    """Add constraints for Combination 1: T_stop = T_stable = T_start = 0"""

    if obj.minimum_power is None or obj.maximum_power is None:
        raise ValueError("minimum_power and maximum_power cannot be None")

    prev_time = time - parameters.timestep

    power_level_var = model.get_variable(f"{obj.name}_power_level_{time}")
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

    model.add_constraint(obj.turned_on.get_value(time) <= 1 - obj.off_var.get_value(time))
    model.add_constraint(obj.turned_on.get_value(time) <= obj.off_var.get_value(prev_time))
    model.add_constraint(
        obj.turned_on.get_value(time) >= obj.off_var.get_value(prev_time) - obj.off_var.get_value(time)
    )

    model.add_constraint(obj.turned_off.get_value(time) <= 1 - obj.off_var.get_value(prev_time))
    model.add_constraint(obj.turned_off.get_value(time) <= obj.off_var.get_value(time))
    model.add_constraint(
        obj.turned_off.get_value(time) >= obj.off_var.get_value(time) - obj.off_var.get_value(prev_time)
    )

    model.add_constraint(
        obj.off_var.get_value(time) + obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time) == 1
    )

    if obj._T_on >= 2:
        for s in range(1, obj._T_on):
            local_time = time - s * parameters.timestep
            model.add_constraint(
                obj.turned_on.get_value(local_time) <= obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time)
            )

    if obj._T_off >= 2:
        for s in range(1, obj._T_off):
            local_time = time - s * parameters.timestep
            model.add_constraint(obj.turned_off.get_value(local_time) <= obj.off_var.get_value(time))

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

    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - obj.off_var.get_value(time)))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - obj.off_var.get_value(time)))
    model.add_constraint(reserves_up_var <= max_power * (1 - obj.off_var.get_value(time)))
    model.add_constraint(reserves_down_var <= max_power * (1 - obj.off_var.get_value(time)))

    model.add_constraint(
        power_level_var >= min_power * (obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time))
    )
    model.add_constraint(
        power_level_var <= max_power * (obj.on_up_var.get_value(time) + obj.on_down_var.get_value(time))
    )

    if time in obj.optimisation_time_window[:-1]:
        if obj._Delta_Q > 0:  # Finite gradient
            # Upward gradient
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q * obj.on_up_var.get_value(prev_time)
                + obj._Delta_Q_unconstrained * obj.turned_on.get_value(time)
            )
            # Downward gradient
            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q * obj.on_down_var.get_value(prev_time)
                - obj._Delta_Q_unconstrained * obj.turned_off.get_value(time)
            )
        elif obj._Delta_Q == 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= obj._Delta_Q_unconstrained * obj.on_down_var.get_value(prev_time)
                + obj._Delta_Q_unconstrained * obj.turned_on.get_value(time)
            )
            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -obj._Delta_Q_unconstrained * obj.on_down_var.get_value(prev_time)
                - obj._Delta_Q_unconstrained * obj.turned_off.get_value(time)
            )
