"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal unit combination 3: T_start >= 1, T_stop = T_stable = 0
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
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
    extended_start_date: DateTime,
    day_zero: bool,
    **kwargs,
) -> None:
    """Combination 3: T_stop=0, T_start=0, T_stable>=1

    Args:
        thermal_unit: The thermal unit to initialize
        model: The optimization model
        parameters: Portfolio optimization parameters
        extended_start_date: The extended start date for initialization
        day_zero: Whether this is day zero (no historical data)
        **kwargs: Additional arguments including:
            - power_timeseries: Historical power data (optional for day_zero, required otherwise)
            - initial_times: List of times to initialize
            - stable_initial_times: List of stable times to initialize
    """
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(thermal_unit, model, time)
            initialize_day_zero_gradient_vars(thermal_unit, model, time)

        for time in kwargs.get("stable_initial_times", []):
            initialize_day_zero_stable_vars(thermal_unit, model, time)

        power_ts = kwargs.get("power_timeseries")
        if isinstance(power_ts, Timeseries):
            initialize_gradient_initial_conditions(thermal_unit, model, power_ts, parameters)

    else:
        power_timeseries = kwargs.get("power_timeseries")
        if not isinstance(power_timeseries, Timeseries):
            raise ValueError("power_timeseries is required in kwargs when day_zero is False")
        if thermal_unit.minimum_power is None:
            raise ValueError("minimum_power is required when day_zero is False")

        for time in kwargs.get("initial_times", []):
            power_at_time = power_timeseries.get_value(time)

            # Get variables
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{time}")
            turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{time}")
            turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{time}")

            # Set OFF state based on power level
            if power_at_time > 0:
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{time}")
            else:
                model.add_constraint(off_var == 1, f"init_off_{thermal_unit.name}_{time}")

            # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
            model.add_constraint(turned_on_var == 0, f"init_turned_on_{thermal_unit.name}_{time}")
            model.add_constraint(turned_off_var == 0, f"init_turned_off_{thermal_unit.name}_{time}")

            # Reconstruct transitions for non-initial times
            if time != extended_start_date:
                prev_time = time - parameters.timestep
                # Detect turn off: was ON -> now OFF
                if (
                    model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{time}").lower_bound
                    - model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{prev_time}").lower_bound
                    == 1
                ):
                    model.add_constraint(turned_off_var == 1, f"init_turned_off_{thermal_unit.name}_{time}")

                # Detect turn on: was OFF -> now ON
                elif (
                    model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{time}").lower_bound
                    - model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{prev_time}").lower_bound
                    == -1
                ):
                    model.add_constraint(turned_on_var == 1, f"init_turned_on_{thermal_unit.name}_{time}")

        for time in kwargs.get("stable_initial_times", []):
            if model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{time}").lower_bound == 0:
                next_time = time + parameters.timestep
                current_power = power_timeseries.get_value(time)
                next_power = (
                    power_timeseries.get_value(next_time) if next_time in power_timeseries.index else current_power
                )

                # Get stable state variables
                on_flat_var = model.get_variable(f"ON_FLAT_{thermal_unit.name}_{time}")
                on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{time}")
                on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{time}")
                stable_var = model.get_variable(f"stable_{time}_{thermal_unit.name}")
                entered_up_var = model.get_variable(f"entered_up_{time}_{thermal_unit.name}")
                entered_down_var = model.get_variable(f"entered_down_{time}_{thermal_unit.name}")

                # Initialize auxiliary variables to 0
                model.add_constraint(stable_var == 0, f"init_stable_{thermal_unit.name}_{time}")
                model.add_constraint(entered_up_var == 0, f"init_entered_up_{thermal_unit.name}_{time}")
                model.add_constraint(entered_down_var == 0, f"init_entered_down_{thermal_unit.name}_{time}")

                # Set stable state variables based on power trend (only if unit is ON)
                off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{time}")
                if current_power > 0:
                    if current_power < next_power:
                        # Power is increasing
                        model.add_constraint(on_up_var == 1, f"init_on_up_{thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{time}")
                        model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{time}")
                    elif current_power > next_power:
                        # Power is decreasing
                        model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 1, f"init_on_down_{thermal_unit.name}_{time}")
                        model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{time}")
                    else:
                        # Power is stable
                        model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{time}")
                        model.add_constraint(on_flat_var == 1, f"init_on_flat_{thermal_unit.name}_{time}")

                # Detect state transitions for non-initial times
                if time != extended_start_date:
                    prev_time = time - parameters.timestep
                    if (
                        model.get_constraint_bounds(f"init_on_flat_{thermal_unit.name}_{time}").lower_bound
                        - model.get_constraint_bounds(f"init_on_flat_{thermal_unit.name}_{prev_time}").lower_bound
                        == 1
                    ):
                        model.add_constraint(stable_var == 1, f"init_stable_{thermal_unit.name}_{time}")

                    if (
                        model.get_constraint_bounds(f"init_on_up_{thermal_unit.name}_{time}").lower_bound
                        - model.get_constraint_bounds(f"init_on_up_{thermal_unit.name}_{prev_time}").lower_bound
                        == 1
                    ):
                        model.add_constraint(entered_up_var == 1, f"init_entered_up_{thermal_unit.name}_{time}")

                    if (
                        model.get_constraint_bounds(f"init_on_down_{thermal_unit.name}_{time}").lower_bound
                        - model.get_constraint_bounds(f"init_on_down_{thermal_unit.name}_{prev_time}").lower_bound
                        == 1
                    ):
                        model.add_constraint(entered_down_var == 1, f"init_entered_down_{thermal_unit.name}_{time}")

        initialize_gradient_initial_conditions(thermal_unit, model, power_timeseries, parameters)


def add_constraints(
    thermal_unit: ThermalPO, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
) -> None:
    """Add constraints for Combination 3: T_start = 0, T_stop = T_stable >= 1"""

    if thermal_unit.minimum_power is None or thermal_unit.maximum_power is None:
        raise ValueError("minimum_power and maximum_power cannot be None")

    prev_time = time - parameters.timestep

    # Get variables
    off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{time}")
    on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{time}")
    on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{time}")
    on_flat_var = model.get_variable(f"ON_FLAT_{thermal_unit.name}_{time}")
    turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{time}")
    turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{time}")
    stable_var = model.get_variable(f"stable_{time}_{thermal_unit.name}")
    entered_up_var = model.get_variable(f"entered_up_{time}_{thermal_unit.name}")
    entered_down_var = model.get_variable(f"entered_down_{time}_{thermal_unit.name}")
    power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{time}")

    # Gradient auxiliary variables
    up_grad_var = model.get_variable(f"UP_grad_{time}_{thermal_unit.name}")
    aux_up_grad_var = model.get_variable(f"aux_up_grad_{time}_{thermal_unit.name}")
    down_grad_var = model.get_variable(f"DOWN_grad_{time}_{thermal_unit.name}")
    aux_down_grad_var = model.get_variable(f"aux_down_grad_{time}_{thermal_unit.name}")

    # Previous time variables
    off_prev_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{prev_time}")
    on_up_prev_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{prev_time}")
    on_down_prev_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{prev_time}")
    on_flat_prev_var = model.get_variable(f"ON_FLAT_{thermal_unit.name}_{prev_time}")
    power_level_prev_var = model.get_variable(f"{thermal_unit.name}_power_level_{prev_time}")
    on_up_prev_2_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{prev_time - parameters.timestep}")
    on_down_prev_2_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{prev_time - parameters.timestep}")

    # Reserve variables
    reserves_up_var = model.get_variable(f"reserves_up_{thermal_unit.name}_{time}")
    reserves_down_var = model.get_variable(f"reserves_down_{thermal_unit.name}_{time}")
    automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{thermal_unit.name}_{time}")
    automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{thermal_unit.name}_{time}")
    unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{thermal_unit.name}_{time}")
    unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{thermal_unit.name}_{time}")
    relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{thermal_unit.name}_{time}")

    max_power = thermal_unit.maximum_power.get_value(time)
    min_power = thermal_unit.minimum_power.get_value(time)
    maximum_automated = get_maximum_automated(thermal_unit)

    model.add_constraint(turned_on_var <= 1 - off_var)
    model.add_constraint(turned_on_var <= off_prev_var)
    model.add_constraint(turned_on_var >= off_prev_var - off_var)

    model.add_constraint(turned_off_var <= 1 - off_prev_var)
    model.add_constraint(turned_off_var <= off_var)
    model.add_constraint(turned_off_var >= off_var - off_prev_var)

    model.add_constraint(stable_var <= 1 - on_flat_prev_var)
    model.add_constraint(stable_var <= on_flat_var)
    model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var)

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

    model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var == 1)

    model.add_constraint(on_up_prev_var + on_down_var <= 1)
    model.add_constraint(on_down_prev_var + on_up_var <= 1)

    if time == thermal_unit.optimisation_time_window[0]:
        model.add_constraint(off_prev_var + on_up_prev_var + on_down_prev_var + on_flat_prev_var == 1)
        model.add_constraint(on_up_prev_2_var + on_down_prev_var <= 1)
        model.add_constraint(on_down_prev_2_var + on_up_prev_var <= 1)

    if thermal_unit._T_on >= 2:
        for s in range(1, thermal_unit._T_on):
            local_time = time - s * parameters.timestep
            turned_on_local_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

    if thermal_unit._T_off >= 2:
        for s in range(1, thermal_unit._T_off):
            local_time = time - s * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= off_var)

    if thermal_unit._T_stable >= 2:
        for s in range(1, thermal_unit._T_stable - 1):
            local_time = time - s * parameters.timestep
            stable_local_var = model.get_variable(f"stable_{local_time}_{thermal_unit.name}")
            model.add_constraint(stable_local_var <= on_flat_var)

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

    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var))

    model.add_constraint(reserves_up_var <= max_power * (1 - off_var - on_up_var - on_down_var))
    model.add_constraint(reserves_down_var <= max_power * (1 - off_var - on_up_var - on_down_var))

    model.add_constraint(power_level_var >= min_power * (on_up_var + on_down_var + on_flat_var))
    model.add_constraint(power_level_var <= max_power * (on_up_var + on_down_var + on_flat_var))

    if time in thermal_unit.optimisation_time_window[:-1]:
        if thermal_unit._Delta_Q > 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= thermal_unit._Delta_Q * entered_up_var
                + up_grad_var
                + down_grad_var
                + thermal_unit._Delta_Q_unconstrained * turned_on_var
            )

            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -thermal_unit._Delta_Q * entered_down_var
                + up_grad_var
                + down_grad_var
                - thermal_unit._Delta_Q_unconstrained * turned_off_var
            )
        elif thermal_unit._Delta_Q == 0:
            model.add_constraint(
                power_level_var - power_level_prev_var
                <= thermal_unit._Delta_Q_unconstrained * entered_up_var
                + up_grad_var
                + down_grad_var
                + thermal_unit._Delta_Q_unconstrained * turned_on_var
            )
            model.add_constraint(
                power_level_var - power_level_prev_var
                >= -thermal_unit._Delta_Q_unconstrained * entered_down_var
                + up_grad_var
                + down_grad_var
                - thermal_unit._Delta_Q_unconstrained * turned_off_var
            )
