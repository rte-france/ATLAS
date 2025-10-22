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
)
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.solver.solver_interface import OptimisationModel


def add_initial_conditions(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
    current_time: DateTime,
    extended_start_date: DateTime,
    power_timeseries: Timeseries | None,
    day_zero: bool,
) -> None:
    """Combination 3: T_stop=False, T_start=True, T_stable=False"""
    if day_zero:
        # DayZero case: All units start OFF
        initialize_day_zero_core(thermal_unit, model, current_time)
        initialize_day_zero_stable_vars(thermal_unit, model, parameters, current_time)
        initialize_day_zero_gradient_vars(thermal_unit, model, current_time)

    else:
        # Non-dayZero case: Initialize based on power history
        if current_time in power_timeseries.index:
            last_power = power_timeseries.get_value(current_time)

            # Get variables
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{current_time}")
            turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{current_time}")
            turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{current_time}")
            power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{current_time}")

            # Fix power level to historical value
            model.add_constraint(power_level_var == last_power, f"init_power_{thermal_unit.name}_{current_time}")

            # Set OFF state based on power level
            if last_power > 0:
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{current_time}")
            else:
                model.add_constraint(off_var == 1, f"init_off_{thermal_unit.name}_{current_time}")

            # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
            model.add_constraint(turned_on_var == 0, f"init_turned_on_{thermal_unit.name}_{current_time}")
            model.add_constraint(turned_off_var == 0, f"init_turned_off_{thermal_unit.name}_{current_time}")

            # Reconstruct transitions for non-initial times
            if current_time != extended_start_date:
                prev_time = current_time - parameters.timestep
                if prev_time in power_timeseries.index:
                    prev_power = power_timeseries.get_value(prev_time)

                    # Detect turn off: was ON -> now OFF
                    if prev_power > 0 and last_power == 0:
                        model.add_constraint(turned_off_var == 1, f"init_turned_off_{thermal_unit.name}_{current_time}")

                    # Detect turn on: was OFF -> now ON
                    elif prev_power == 0 and last_power > 0:
                        model.add_constraint(turned_on_var == 1, f"init_turned_on_{thermal_unit.name}_{current_time}")

        # Handle stable-specific variables for non-dayZero (only if not the last timestep)
        next_time = current_time + parameters.timestep
        if current_time in power_timeseries.index and next_time <= parameters.end_date:
            current_power = power_timeseries.get_value(current_time)
            next_power = power_timeseries.get_value(next_time) if next_time in power_timeseries.index else current_power

            # Get stable state variables
            on_flat_var = model.get_variable(f"ON_FLAT_{thermal_unit.name}_{current_time}")
            on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{current_time}")
            on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{current_time}")
            stable_var = model.get_variable(f"stable_{current_time}_{thermal_unit.name}")
            entered_up_var = model.get_variable(f"entered_up_{current_time}_{thermal_unit.name}")
            entered_down_var = model.get_variable(f"entered_down_{current_time}_{thermal_unit.name}")

            # Initialize auxiliary variables to 0
            model.add_constraint(stable_var == 0, f"init_stable_{thermal_unit.name}_{current_time}")
            model.add_constraint(entered_up_var == 0, f"init_entered_up_{thermal_unit.name}_{current_time}")
            model.add_constraint(entered_down_var == 0, f"init_entered_down_{thermal_unit.name}_{current_time}")

            # Set stable state variables based on power trend (only if unit is ON)
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{current_time}")
            if current_power > 0:
                if current_power < next_power:
                    # Power is increasing
                    model.add_constraint(on_up_var == 1, f"init_on_up_{thermal_unit.name}_{current_time}")
                    model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")
                    model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{current_time}")
                elif current_power > next_power:
                    # Power is decreasing
                    model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
                    model.add_constraint(on_down_var == 1, f"init_on_down_{thermal_unit.name}_{current_time}")
                    model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{current_time}")
                else:
                    # Power is stable
                    model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
                    model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")
                    model.add_constraint(on_flat_var == 1, f"init_on_flat_{thermal_unit.name}_{current_time}")

                # Detect state transitions for non-initial times
                if current_time != extended_start_date:
                    prev_time = current_time - parameters.timestep
                    if prev_time in power_timeseries.index:
                        # Detect entering FLAT state
                        prev_next_time = prev_time + parameters.timestep
                        prev_power = power_timeseries.get_value(prev_time)
                        prev_next_power = (
                            power_timeseries.get_value(prev_next_time)
                            if prev_next_time in power_timeseries.index
                            else prev_power
                        )

                        prev_was_flat = prev_power == prev_next_power and prev_power > 0
                        current_is_flat = current_power == next_power and current_power > 0

                        if not prev_was_flat and current_is_flat:
                            model.add_constraint(stable_var == 1, f"init_stable_{thermal_unit.name}_{current_time}")

                        # Detect entering UP state
                        prev_was_up = prev_power < prev_next_power
                        current_is_up = current_power < next_power

                        if not prev_was_up and current_is_up:
                            model.add_constraint(
                                entered_up_var == 1, f"init_entered_up_{thermal_unit.name}_{current_time}"
                            )

                        # Detect entering DOWN state
                        prev_was_down = prev_power > prev_next_power
                        current_is_down = current_power > next_power

                        if not prev_was_down and current_is_down:
                            model.add_constraint(
                                entered_down_var == 1, f"init_entered_down_{thermal_unit.name}_{current_time}"
                            )

        # Initialize gradient auxiliaries for the current time step
        # Only apply gradient logic if current time is at start_date - timestep
        start_date_minus_one = parameters.start_date - parameters.timestep
        if current_time == start_date_minus_one:
            start_date_minus_two = parameters.start_date - 2 * parameters.timestep

            if start_date_minus_one in power_timeseries.index and start_date_minus_two in power_timeseries.index:
                power_minus_one = power_timeseries.get_value(start_date_minus_one)
                power_minus_two = power_timeseries.get_value(start_date_minus_two)

                # Get gradient auxiliary variables
                u_var = model.get_variable(f"UP_grad_{start_date_minus_one}_for_{thermal_unit.name}")
                d_var = model.get_variable(f"DOWN_grad_{start_date_minus_one}_{thermal_unit.name}")

                # Calculate gradient values based on power trend
                power_diff = power_minus_one - power_minus_two

                # U gradient: only non-zero if unit was in UP state at both time steps
                if power_minus_two > 0 and power_minus_one > 0 and power_minus_two < power_minus_one:
                    model.add_constraint(u_var == power_diff, f"init_u_grad_{thermal_unit.name}_{start_date_minus_one}")
                else:
                    model.add_constraint(u_var == 0, f"init_u_grad_{thermal_unit.name}_{start_date_minus_one}")

                # D gradient: only non-zero if unit was in DOWN state at both time steps
                if power_minus_two > 0 and power_minus_one > 0 and power_minus_two > power_minus_one:
                    model.add_constraint(d_var == power_diff, f"init_d_grad_{thermal_unit.name}_{start_date_minus_one}")
                else:
                    model.add_constraint(d_var == 0, f"init_d_grad_{thermal_unit.name}_{start_date_minus_one}")


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
    up_grad_var = model.get_variable(f"UP_grad_{time}_for_{thermal_unit.name}")
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
    if time in parameters.thermal_op_times[:-1]:  # Not the last time step
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
