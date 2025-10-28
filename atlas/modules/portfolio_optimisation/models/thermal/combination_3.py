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
    power_timeseries: Timeseries | None,
    day_zero: bool,
    **kwargs,
) -> None:
    """Combination 3: T_stop=0, T_start=0, T_stable>=1"""
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(thermal_unit, model, time)
            initialize_day_zero_gradient_vars(thermal_unit, model, time)

        for time in kwargs.get("stable_initial_times", []):
            initialize_day_zero_stable_vars(thermal_unit, model, time)

        initialize_gradient_initial_conditions(thermal_unit, model, power_timeseries, parameters)

    else:
        for time in kwargs.get("initial_times", []):
            last_power = power_timeseries.get_value(time)

            # Get variables
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{time}")
            turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{time}")
            turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{time}")

            # Set OFF state based on power level
            if last_power > 0:
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
    """Add constraints for Combination 3: T_start >= 1, T_stop = T_stable = 0

    This combination represents the scenario where:
    - T_start >= 1: Minimum start time requirement (startup sequence)
    - T_stop = 0: No minimum stop time requirement
    - T_stable = 0: No stable operation time requirement

    Args:
        thermal_unit: The thermal unit to add constraints for
        time: Current time step
        model: Optimization model to add constraints to
        parameters: Portfolio optimization parameters
    """
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
    power_prev_var = model.get_variable(f"{thermal_unit.name}_power_level_{prev_time}")

    # Reserve variables
    reserves_up_var = model.get_variable(f"reserves_up_{thermal_unit.name}_{time}")
    reserves_down_var = model.get_variable(f"reserves_down_{thermal_unit.name}_{time}")
    automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{thermal_unit.name}_{time}")
    automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{thermal_unit.name}_{time}")
    unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{thermal_unit.name}_{time}")
    unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{thermal_unit.name}_{time}")
    relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{thermal_unit.name}_{time}")

    # Power bounds
    q_upper = thermal_unit.maximum_power.get_value(time)
    q_lower = thermal_unit.minimum_power.get_value(time)
    maximum_automated = get_maximum_automated(thermal_unit)

    # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

    # Constraints on turned_on (sec. 6.1.1)
    model.add_constraint(turned_on_var <= 1 - off_var)
    model.add_constraint(turned_on_var <= off_prev_var)
    model.add_constraint(turned_on_var >= off_prev_var - off_var)

    # Constraints on turned_off (sec. 6.1.2)
    model.add_constraint(turned_off_var <= 1 - off_prev_var)
    model.add_constraint(turned_off_var <= off_var)
    model.add_constraint(turned_off_var >= off_var - off_prev_var)

    # Constraints on stable (sec. 6.1.3)
    model.add_constraint(stable_var <= 1 - on_flat_prev_var)
    model.add_constraint(stable_var <= on_flat_var)
    model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var)

    # Constraints on entered_up
    model.add_constraint(entered_up_var <= 1 - on_up_prev_var)
    model.add_constraint(entered_up_var <= on_up_var)
    model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var)

    # Constraints on entered_down
    model.add_constraint(entered_down_var <= 1 - on_down_prev_var)
    model.add_constraint(entered_down_var <= on_down_var)
    model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var)

    # UP and DOWN "semi-continuous" variables for the gradient
    # First stage: tilde_U and tilde_D (aux_up_grad and aux_down_grad)
    # tilde_U (aux_up_grad)
    model.add_constraint(aux_up_grad_var <= q_upper * on_up_prev_var)
    model.add_constraint(aux_up_grad_var >= q_lower * on_up_prev_var)
    model.add_constraint(aux_up_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_up_prev_var))
    model.add_constraint(aux_up_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_up_prev_var))

    # tilde_D (aux_down_grad)
    model.add_constraint(aux_down_grad_var <= q_upper * on_down_prev_var)
    model.add_constraint(aux_down_grad_var >= q_lower * on_down_prev_var)
    model.add_constraint(aux_down_grad_var <= power_level_var - power_prev_var - q_lower * (1 - on_down_prev_var))
    model.add_constraint(aux_down_grad_var >= power_level_var - power_prev_var - q_upper * (1 - on_down_prev_var))

    # Second stage: U and D (up_grad and down_grad)
    # U (up_grad)
    model.add_constraint(up_grad_var <= q_upper * on_up_var)
    model.add_constraint(up_grad_var >= q_lower * on_up_var)
    model.add_constraint(up_grad_var <= aux_up_grad_var - q_lower * (1 - on_up_var))
    model.add_constraint(up_grad_var >= aux_up_grad_var - q_upper * (1 - on_up_var))

    # D (down_grad)
    model.add_constraint(down_grad_var <= q_upper * on_down_var)
    model.add_constraint(down_grad_var >= q_lower * on_down_var)
    model.add_constraint(down_grad_var <= aux_down_grad_var - q_lower * (1 - on_down_var))
    model.add_constraint(down_grad_var >= aux_down_grad_var - q_upper * (1 - on_down_var))

    # B. CONSTRAINTS ON THE STATE VARIABLES

    # Mutual exclusion constraint - now includes ON_FLAT state
    model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var == 1)

    # Transition constraints
    # UP-DOWN and DOWN-UP transitions are forbidden
    model.add_constraint(on_up_prev_var + on_down_var <= 1)
    model.add_constraint(on_down_prev_var + on_up_var <= 1)

    # Minimum time constraints
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

    # C. CONSTRAINTS ON THE CONTROL VARIABLE

    # Reserve "fill up" constraints
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

    # Relaxed reserve disabling condition - includes ON_FLAT state
    model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_flat_var - on_down_var))

    # Reserve availability constraints
    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var))
    # Manual reserves only available in FLAT state (not during ramping)
    model.add_constraint(reserves_up_var <= q_upper * (1 - off_var - on_up_var - on_down_var))
    model.add_constraint(reserves_down_var <= q_upper * (1 - off_var - on_up_var - on_down_var))

    # Power output bounds - includes ON_FLAT state
    model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var + on_flat_var))
    model.add_constraint(power_level_var <= q_upper * (on_up_var + on_down_var + on_flat_var))

    # Power gradients with gradient auxiliary variables
    if time in thermal_unit.optimisation_time_window[:-1]:  # Not the last time step
        if thermal_unit._Delta_Q > 0:  # Finite gradient
            # Upward gradient
            model.add_constraint(
                power_level_var - power_prev_var
                <= thermal_unit._Delta_Q * entered_up_var
                + up_grad_var
                + down_grad_var
                + thermal_unit._Delta_Q_unconstrained * turned_on_var
            )
            # Downward gradient
            model.add_constraint(
                power_level_var - power_prev_var
                >= -thermal_unit._Delta_Q * entered_down_var
                + up_grad_var
                + down_grad_var
                - thermal_unit._Delta_Q_unconstrained * turned_off_var
            )
        elif thermal_unit._Delta_Q == 0:  # Infinite gradient
            model.add_constraint(
                power_level_var - power_prev_var
                <= thermal_unit._Delta_Q_unconstrained * entered_up_var
                + up_grad_var
                + down_grad_var
                + thermal_unit._Delta_Q_unconstrained * turned_on_var
            )
            model.add_constraint(
                power_level_var - power_prev_var
                >= -thermal_unit._Delta_Q_unconstrained * entered_down_var
                + up_grad_var
                + down_grad_var
                - thermal_unit._Delta_Q_unconstrained * turned_off_var
            )

    # Daily energy constraints (if applicable)
    if thermal_unit.has_daily_energy_constraint:
        # This would need to be implemented at a higher level since it requires all time steps for a day
        pass
