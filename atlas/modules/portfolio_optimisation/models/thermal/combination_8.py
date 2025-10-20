"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal unit initial conditions - Combination 8: T_stop=True, T_start=True, T_stable=True
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

from atlas.math.timeseries import Timeseries

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO

from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.solver.solver_interface import OptimisationModel


def add_initial_conditions(
    thermal_unit: ThermalPO,
    model: OptimisationModel,
    parameters: PortfolioOptimisationParameters,
    current_time: DateTime,
    extended_start_date: DateTime,
    power_history: Timeseries | None,
    day_zero: bool,
) -> None:
    """Combination 8: T_stop=True, T_start=True, T_stable=True"""
    if day_zero:
        # DayZero case: All units start OFF
        # Get state variables
        off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{current_time}")
        stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{current_time}")
        start_var = model.get_variable(f"ON_START_{thermal_unit.name}_{current_time}")
        turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{current_time}")
        turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{current_time}")
        power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{current_time}")

        # Fix state variables using equality constraints
        model.add_constraint(off_var == 1, f"init_off_{thermal_unit.name}_{current_time}")
        model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")
        model.add_constraint(start_var == 0, f"init_start_{thermal_unit.name}_{current_time}")

        # Fix auxiliary variables
        model.add_constraint(turned_on_var == 0, f"init_turned_on_{thermal_unit.name}_{current_time}")
        model.add_constraint(turned_off_var == 0, f"init_turned_off_{thermal_unit.name}_{current_time}")

        # Fix power level to 0
        model.add_constraint(power_level_var == 0, f"init_power_{thermal_unit.name}_{current_time}")

        # Initialize stable-specific variables for dayZero (only if not the last timestep)
        next_time = current_time + parameters.timestep
        if next_time <= parameters.end_date:
            # Get stable state variables
            on_flat_var = model.get_variable(f"ON_FLAT_{thermal_unit.name}_{current_time}")
            on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{current_time}")
            on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{current_time}")
            stable_var = model.get_variable(f"stable_{current_time}_{thermal_unit.name}")
            entered_up_var = model.get_variable(f"entered_up_{current_time}_{thermal_unit.name}")
            entered_down_var = model.get_variable(f"entered_down_{current_time}_{thermal_unit.name}")
            flat_down_stop_var = model.get_variable(f"flat_down_stop_{current_time}_{thermal_unit.name}")

            # Fix stable state variables
            model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{current_time}")
            model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
            model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")

            # Fix stable auxiliary variables
            model.add_constraint(stable_var == 0, f"init_stable_{thermal_unit.name}_{current_time}")
            model.add_constraint(entered_up_var == 0, f"init_entered_up_{thermal_unit.name}_{current_time}")
            model.add_constraint(entered_down_var == 0, f"init_entered_down_{thermal_unit.name}_{current_time}")
            model.add_constraint(flat_down_stop_var == 0, f"init_flat_down_stop_{thermal_unit.name}_{current_time}")

        # Initialize gradient auxiliaries to 0 for dayZero
        u_var = model.get_variable(f"UP_grad_{current_time}_for_{thermal_unit.name}")
        d_var = model.get_variable(f"DOWN_grad_{current_time}_{thermal_unit.name}")
        tilde_u_var = model.get_variable(f"aux_up_grad_{current_time}_{thermal_unit.name}")
        tilde_d_var = model.get_variable(f"aux_down_grad_{current_time}_{thermal_unit.name}")

        model.add_constraint(u_var == 0, f"init_u_grad_{thermal_unit.name}_{current_time}")
        model.add_constraint(d_var == 0, f"init_d_grad_{thermal_unit.name}_{current_time}")
        model.add_constraint(tilde_u_var == 0, f"init_tilde_u_grad_{thermal_unit.name}_{current_time}")
        model.add_constraint(tilde_d_var == 0, f"init_tilde_d_grad_{thermal_unit.name}_{current_time}")

    else:
        # Non-dayZero case: Initialize based on power history
        if current_time in power_history.index:
            last_power = power_history.get_value(current_time)
            min_power = thermal_unit.minimum_power.get_value(current_time)

            # Get variables
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{current_time}")
            stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{current_time}")
            start_var = model.get_variable(f"ON_START_{thermal_unit.name}_{current_time}")
            turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{current_time}")
            turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{current_time}")
            power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{current_time}")

            # Fix power level to historical value
            model.add_constraint(power_level_var == last_power, f"init_power_{thermal_unit.name}_{current_time}")

            # Set state variables based on power level relative to minimum power
            if last_power >= min_power:
                # Unit is ON and above minimum power (normal operation)
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{current_time}")
                model.add_constraint(start_var == 0, f"init_start_{thermal_unit.name}_{current_time}")
                model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")
            elif last_power > 0:
                # Unit is ON but below minimum power (startup or shutdown phase)
                # Initially set both START and STOP to 1, distinguish later based on trend
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{current_time}")
                model.add_constraint(start_var == 1, f"init_start_{thermal_unit.name}_{current_time}")
                model.add_constraint(stop_var == 1, f"init_stop_{thermal_unit.name}_{current_time}")
            else:
                # Unit is completely OFF
                model.add_constraint(off_var == 1, f"init_off_{thermal_unit.name}_{current_time}")
                model.add_constraint(start_var == 0, f"init_start_{thermal_unit.name}_{current_time}")
                model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")

            # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
            model.add_constraint(turned_on_var == 0, f"init_turned_on_{thermal_unit.name}_{current_time}")
            model.add_constraint(turned_off_var == 0, f"init_turned_off_{thermal_unit.name}_{current_time}")

            # Distinguish between startup and shutdown for intermediate power levels
            if current_time != extended_start_date and 0 < last_power < min_power:
                prev_time = current_time - parameters.timestep
                if prev_time in power_history.index:
                    prev_power = power_history.get_value(prev_time)

                    # If power is increasing, we are starting up
                    if last_power > prev_power:
                        model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")
                        model.add_constraint(start_var == 1, f"init_start_{thermal_unit.name}_{current_time}")
                    # If power is decreasing, we are shutting down
                    elif last_power < prev_power:
                        model.add_constraint(stop_var == 1, f"init_stop_{thermal_unit.name}_{current_time}")
                        model.add_constraint(start_var == 0, f"init_start_{thermal_unit.name}_{current_time}")
                    # If power is stable, keep both (handled by constraints)

                # Reconstruct transitions for non-initial times
                if current_time != extended_start_date:
                    prev_time = current_time - parameters.timestep
                    if prev_time in power_history.index:
                        prev_power = power_history.get_value(prev_time)

                        # Detect turn off: entering STOP state
                        if prev_power > 0 and last_power == 0:
                            model.add_constraint(
                                turned_off_var == 1, f"init_turned_off_{thermal_unit.name}_{current_time}"
                            )

                        # Detect turn on: entering START state
                        elif prev_power == 0 and last_power > 0:
                            model.add_constraint(
                                turned_on_var == 1, f"init_turned_on_{thermal_unit.name}_{current_time}"
                            )

        # Handle stable-specific variables for non-dayZero
        if current_time in power_history.index:
            current_power = power_history.get_value(current_time)
            next_time = current_time + parameters.timestep
            next_power = power_history.get_value(next_time) if next_time in power_history.index else current_power
            min_power = thermal_unit.minimum_power.get_value(current_time)

            # Get stable state variables
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{current_time}")
            start_var = model.get_variable(f"ON_START_{thermal_unit.name}_{current_time}")
            stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{current_time}")
            on_flat_var = model.get_variable(f"ON_FLAT_{thermal_unit.name}_{current_time}")
            on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{current_time}")
            on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{current_time}")
            stable_var = model.get_variable(f"stable_{current_time}_{thermal_unit.name}")
            entered_up_var = model.get_variable(f"entered_up_{current_time}_{thermal_unit.name}")
            entered_down_var = model.get_variable(f"entered_down_{current_time}_{thermal_unit.name}")
            flat_down_stop_var = model.get_variable(f"flat_down_stop_{current_time}_{thermal_unit.name}")

            # Initialize auxiliary variables to 0
            model.add_constraint(stable_var == 0, f"init_stable_{thermal_unit.name}_{current_time}")
            model.add_constraint(entered_up_var == 0, f"init_entered_up_{thermal_unit.name}_{current_time}")
            model.add_constraint(entered_down_var == 0, f"init_entered_down_{thermal_unit.name}_{current_time}")

            # Set stable state variables based on unit state
            if current_power == 0:
                # Unit is OFF
                model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{current_time}")
            elif current_power > 0 and current_power < min_power:
                # Unit is in START or STOP state - no UP/DOWN/FLAT allowed
                model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{current_time}")
            else:
                # Unit is ON and above minimum power - determine trend
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
                if current_time != extended_start_date and current_power >= min_power:
                    prev_time = current_time - parameters.timestep
                    if prev_time in power_history.index:
                        # Detect entering FLAT state
                        prev_next_time = prev_time + parameters.timestep
                        prev_power = power_history.get_value(prev_time)
                        prev_next_power = (
                            power_history.get_value(prev_next_time)
                            if prev_next_time in power_history.index
                            else prev_power
                        )
                        prev_min_power = thermal_unit.minimum_power.get_value(prev_time)

                        prev_was_flat = prev_power == prev_next_power and prev_power >= prev_min_power
                        current_is_flat = current_power == next_power and current_power >= min_power

                        if not prev_was_flat and current_is_flat:
                            model.add_constraint(stable_var == 1, f"init_stable_{thermal_unit.name}_{current_time}")

                        # Detect entering UP state
                        prev_was_up = prev_power < prev_next_power and prev_power >= prev_min_power
                        current_is_up = current_power < next_power and current_power >= min_power

                        if not prev_was_up and current_is_up:
                            model.add_constraint(
                                entered_up_var == 1, f"init_entered_up_{thermal_unit.name}_{current_time}"
                            )

                        # Detect entering DOWN state
                        prev_was_down = prev_power > prev_next_power and prev_power >= prev_min_power
                        current_is_down = current_power > next_power and current_power >= min_power

                        if not prev_was_down and current_is_down:
                            model.add_constraint(
                                entered_down_var == 1, f"init_entered_down_{thermal_unit.name}_{current_time}"
                            )

            # Initialize flat_down_stop (if time allows)
            # flat_down_stop = floor((STOP[t] + ON_DOWN[t-1] + ON_FLAT[t-2]) / 3)
            time_minus_1 = current_time - parameters.timestep
            time_minus_2 = current_time - 2 * parameters.timestep

            if time_minus_1 in power_history.index and time_minus_2 in power_history.index:
                power_minus_1 = power_history.get_value(time_minus_1)
                power_minus_2 = power_history.get_value(time_minus_2)
                min_power_minus_1 = thermal_unit.minimum_power.get_value(time_minus_1)
                min_power_minus_2 = thermal_unit.minimum_power.get_value(time_minus_2)

                # Get next powers for trend analysis
                next_time_minus_1 = time_minus_1 + parameters.timestep
                next_time_minus_2 = time_minus_2 + parameters.timestep

                next_power_minus_1 = (
                    power_history.get_value(next_time_minus_1)
                    if next_time_minus_1 in power_history.index
                    else power_minus_1
                )
                next_power_minus_2 = (
                    power_history.get_value(next_time_minus_2)
                    if next_time_minus_2 in power_history.index
                    else power_minus_2
                )

                # Calculate components
                stop_component = (
                    1
                    if (
                        current_power > 0
                        and current_power < min_power
                        and power_minus_1 >= min_power_minus_1
                        and current_power < power_minus_1
                    )
                    else 0
                )
                on_down_component = (
                    1 if (power_minus_1 > next_power_minus_1 and power_minus_1 >= min_power_minus_1) else 0
                )
                on_flat_component = (
                    1 if (power_minus_2 == next_power_minus_2 and power_minus_2 >= min_power_minus_2) else 0
                )

                flat_down_stop_value = (stop_component + on_down_component + on_flat_component) // 3
                model.add_constraint(
                    flat_down_stop_var == flat_down_stop_value,
                    f"init_flat_down_stop_{thermal_unit.name}_{current_time}",
                )
            else:
                model.add_constraint(flat_down_stop_var == 0, f"init_flat_down_stop_{thermal_unit.name}_{current_time}")

        # Initialize gradient auxiliaries and flat_down_stop for the last time step
        # Only initialize if current_time is not the extended start date (implying there's historical data)
        if current_time != extended_start_date:
            start_date_minus_one = parameters.start_date - parameters.timestep
            start_date_minus_two = parameters.start_date - 2 * parameters.timestep
            start_date_minus_three = parameters.start_date - 3 * parameters.timestep

            if start_date_minus_one in power_history.index and start_date_minus_two in power_history.index:
                power_minus_one = power_history.get_value(start_date_minus_one)
                power_minus_two = power_history.get_value(start_date_minus_two)
                min_power_minus_one = thermal_unit.minimum_power.get_value(start_date_minus_one)
                min_power_minus_two = thermal_unit.minimum_power.get_value(start_date_minus_two)

                # Get gradient auxiliary variables
                u_var = model.get_variable(f"UP_grad_{start_date_minus_one}_for_{thermal_unit.name}")
                d_var = model.get_variable(f"DOWN_grad_{start_date_minus_one}_{thermal_unit.name}")

                # Calculate gradient values based on power trend
                power_diff = power_minus_one - power_minus_two

                # U gradient: only non-zero if unit was in UP state at both time steps
                if (
                    power_minus_two >= min_power_minus_two
                    and power_minus_one >= min_power_minus_one
                    and power_minus_two < power_minus_one
                ):
                    model.add_constraint(u_var == power_diff, f"init_u_grad_{thermal_unit.name}_{start_date_minus_one}")
                else:
                    model.add_constraint(u_var == 0, f"init_u_grad_{thermal_unit.name}_{start_date_minus_one}")

                # D gradient: only non-zero if unit was in DOWN state at both time steps
                if (
                    power_minus_two >= min_power_minus_two
                    and power_minus_one >= min_power_minus_one
                    and power_minus_two > power_minus_one
                ):
                    model.add_constraint(d_var == power_diff, f"init_d_grad_{thermal_unit.name}_{start_date_minus_one}")
                else:
                    model.add_constraint(d_var == 0, f"init_d_grad_{thermal_unit.name}_{start_date_minus_one}")

                # Initialize flat_down_stop for start_date_minus_one
                if start_date_minus_three in power_history.index:
                    power_minus_three = power_history.get_value(start_date_minus_three)
                    min_power_minus_three = thermal_unit.minimum_power.get_value(start_date_minus_three)

                    # Get next power for trend analysis at time minus 3
                    next_time_minus_three = start_date_minus_three + parameters.timestep
                    next_power_minus_three = (
                        power_history.get_value(next_time_minus_three)
                        if next_time_minus_three in power_history.index
                        else power_minus_three
                    )

                    # Calculate flat_down_stop components
                    stop_component = (
                        1
                        if (
                            power_minus_one > 0
                            and power_minus_one < min_power_minus_one
                            and power_minus_two >= min_power_minus_two
                            and power_minus_one < power_minus_two
                        )
                        else 0
                    )
                    on_down_component = (
                        1 if (power_minus_two > power_minus_one and power_minus_two >= min_power_minus_two) else 0
                    )
                    on_flat_component = (
                        1
                        if (power_minus_three == next_power_minus_three and power_minus_three >= min_power_minus_three)
                        else 0
                    )

                    flat_down_stop_value = (stop_component + on_down_component + on_flat_component) // 3
                    flat_down_stop_var = model.get_variable(
                        f"flat_down_stop_{start_date_minus_one}_{thermal_unit.name}"
                    )
                    model.add_constraint(
                        flat_down_stop_var == flat_down_stop_value,
                        f"init_flat_down_stop_{thermal_unit.name}_{start_date_minus_one}",
                    )


def add_constraints(
    thermal_unit: ThermalPO, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
) -> None:
    """Add constraints for Combination 8: T_start >= 1, T_stable >= 1, T_stop >= 1

    This combination represents the scenario where:
    - T_start >= 1: Minimum start time requirement (startup sequence)
    - T_stable >= 1: Minimum stable operation time requirement
    - T_stop >= 1: Minimum stop time requirement (shutdown sequence)

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
    start_var = model.get_variable(f"ON_START_{thermal_unit.name}_{time}")
    stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{time}")
    turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{time}")
    turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{time}")
    stable_var = model.get_variable(f"stable_{time}_{thermal_unit.name}")
    entered_up_var = model.get_variable(f"entered_up_{time}_{thermal_unit.name}")
    entered_down_var = model.get_variable(f"entered_down_{time}_{thermal_unit.name}")
    flat_down_stop_var = model.get_variable(f"flat_down_stop_{time}_{thermal_unit.name}")
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
    start_prev_var = model.get_variable(f"ON_START_{thermal_unit.name}_{prev_time}")
    stop_prev_var = model.get_variable(f"STOP_{thermal_unit.name}_{prev_time}")
    power_prev_var = model.get_variable(f"{thermal_unit.name}_power_level_{prev_time}")
    up_grad_prev_var = model.get_variable(f"UP_grad_{prev_time}_for_{thermal_unit.name}")
    down_grad_prev_var = model.get_variable(f"DOWN_grad_{prev_time}_{thermal_unit.name}")
    dd_grad_prev_var = model.get_variable(f"DD_grad_{prev_time}_{thermal_unit.name}")

    # Reserve variables
    reserves_up_var = model.get_variable(f"reserves_up_{thermal_unit.name}_{time}")
    reserves_down_var = model.get_variable(f"reserves_down_{thermal_unit.name}_{time}")
    automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{thermal_unit.name}_{time}")
    automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{thermal_unit.name}_{time}")
    unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{thermal_unit.name}_{time}")
    unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{thermal_unit.name}_{time}")
    relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{thermal_unit.name}_{time}")

    # Power bounds and gradient parameters
    q_upper = thermal_unit.maximum_power.get_value(time)
    q_lower = thermal_unit.minimum_power.get_value(time)
    maximum_automated = get_maximum_automated(thermal_unit)

    # Dual gradient parameters for startup and shutdown
    q_min = thermal_unit.minimum_power.max()
    q_step_up = q_min / thermal_unit._T_start  # Startup gradient step
    q_step_down = q_min / thermal_unit._T_stop  # Shutdown gradient step

    # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

    # Constraints on turned_on - eq. (3)
    model.add_constraint(turned_on_var <= 1 - off_var)
    model.add_constraint(turned_on_var <= off_prev_var)
    model.add_constraint(turned_on_var >= off_prev_var - off_var)

    # Constraints on turned_off (entering STOP state) - eq. (5)
    model.add_constraint(turned_off_var <= 1 - stop_prev_var)
    model.add_constraint(turned_off_var <= stop_var)
    model.add_constraint(turned_off_var >= stop_var - stop_prev_var)

    # Constraints on stable - eq. (6)
    model.add_constraint(stable_var <= 1 - on_flat_prev_var)
    model.add_constraint(stable_var <= on_flat_var)
    model.add_constraint(stable_var >= on_flat_var - on_flat_prev_var)

    # flat_down_stop auxiliary - eq. (22)
    # Detects FLAT(t-2) -> DOWN(t-1) -> STOP(t) path
    two_steps_ago = time - 2 * parameters.timestep
    on_flat_two_prev_var = model.get_variable(f"ON_FLAT_{thermal_unit.name}_{two_steps_ago}")
    model.add_constraint(flat_down_stop_var <= stop_var)
    model.add_constraint(flat_down_stop_var <= on_down_prev_var)
    model.add_constraint(flat_down_stop_var <= on_flat_two_prev_var)
    model.add_constraint(flat_down_stop_var >= stop_var + on_down_prev_var + on_flat_two_prev_var - 2)

    # Constraints on entered_up - eq. (7)
    model.add_constraint(entered_up_var <= 1 - on_up_prev_var)
    model.add_constraint(entered_up_var <= on_up_var)
    model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var)

    # Constraints on entered_down - eq. (8)
    model.add_constraint(entered_down_var <= 1 - on_down_prev_var)
    model.add_constraint(entered_down_var <= on_down_var)
    model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var)

    # UP and DOWN "semi-continuous" variables for the gradient
    # First stage: tilde_U and tilde_D (aux_up_grad and aux_down_grad) - eq. (28) and (30)
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

    # Second stage: U and D (up_grad and down_grad) - eq. (27) and (29)
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

    # DD Gradient auxiliary - eq. (23)
    # Detects if unit is to be stopped at t+1 after being in DOWN state at t and t-1
    if time in parameters.thermal_op_times[:-1]:  # Not the last time step
        model.add_constraint(dd_grad_prev_var <= q_upper * stop_var)
        model.add_constraint(dd_grad_prev_var >= q_lower * stop_var)
        model.add_constraint(dd_grad_prev_var <= down_grad_prev_var - q_lower * (1 - stop_var))
        model.add_constraint(dd_grad_prev_var >= down_grad_prev_var - q_upper * (1 - stop_var))

    # B. CONSTRAINTS ON THE STATE VARIABLES

    # Mutual exclusion constraint - 6 states - eq. (9)
    model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var + stop_var + start_var == 1)

    # Complex transition constraints - most comprehensive set
    # UP-DOWN and DOWN-UP transitions are forbidden - eq. (25)
    model.add_constraint(on_up_prev_var + on_down_var <= 1)
    model.add_constraint(on_down_prev_var + on_up_var <= 1)

    # STOP to ON transitions are forbidden - eq. (13)
    model.add_constraint(stop_prev_var + on_flat_var <= 1)
    model.add_constraint(stop_prev_var + on_down_var <= 1)
    model.add_constraint(stop_prev_var + on_up_var <= 1)

    # ON_UP to STOP transition is forbidden - eq. (21)
    model.add_constraint(on_up_prev_var + stop_var <= 1)

    # OFF to STOP transition is forbidden - eq. (12)
    model.add_constraint(off_prev_var + stop_var <= 1)

    # ON to START transitions are forbidden - eq. (10)
    model.add_constraint(on_up_prev_var + start_var <= 1)
    model.add_constraint(on_down_prev_var + start_var <= 1)
    model.add_constraint(on_flat_prev_var + start_var <= 1)

    # ON to OFF transitions are forbidden
    model.add_constraint(on_up_prev_var + off_var <= 1)
    model.add_constraint(on_down_prev_var + off_var <= 1)
    model.add_constraint(on_flat_prev_var + off_var <= 1)

    # START to OFF transition is forbidden - eq. (11)
    model.add_constraint(start_prev_var + off_var <= 1)

    # START to STOP and STOP to START transitions are forbidden - eq. (14)
    model.add_constraint(start_prev_var + stop_var <= 1)
    model.add_constraint(stop_prev_var + start_var <= 1)

    # Direct OFF to ON transitions are forbidden - eq. (15)
    model.add_constraint(off_prev_var + on_up_var <= 1)
    model.add_constraint(off_prev_var + on_flat_var <= 1)
    model.add_constraint(off_prev_var + on_down_var <= 1)

    # Eviction constraints
    # STOP eviction - forces unit to leave STOP state after T_stop time steps - eq. (19)
    if thermal_unit._T_stop > 1:
        stop_eviction_time = time - (thermal_unit._T_stop - 1) * parameters.timestep
        turned_off_stop_eviction_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{stop_eviction_time}")
        model.add_constraint(turned_off_stop_eviction_var + stop_var <= 1)

    # START eviction - forces unit to leave START state after T_start time steps - eq. (16)
    if thermal_unit._T_start >= 1:
        start_eviction_time = time - (thermal_unit._T_start - 1) * parameters.timestep
        turned_on_start_eviction_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{start_eviction_time}")
        model.add_constraint(turned_on_start_eviction_var + start_var <= 1)

    # Minimum time constraints with all adjustments
    if thermal_unit._T_on >= 2:
        for s in range(1, thermal_unit._T_on):
            # eq. (31) with T_start > 0 - adjusted timing for startup
            local_time = time - (s + thermal_unit._T_start) * parameters.timestep
            turned_on_local_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

    if thermal_unit._T_off >= 2:
        for s in range(1, thermal_unit._T_off):
            # eq. (32) with T_stop > 0 - adjusted timing for shutdown
            local_time = time - (s + thermal_unit._T_stop) * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= off_var)

    if thermal_unit._T_stable >= 2:
        for s in range(1, thermal_unit._T_stable - 1):
            # eq. (26)
            local_time = time - s * parameters.timestep
            stable_local_var = model.get_variable(f"stable_{local_time}_{thermal_unit.name}")
            model.add_constraint(stable_local_var <= on_flat_var)

    # Shutdown ramp constraints - eq. (24)
    if thermal_unit._T_stop >= 2:
        for s in range(1, thermal_unit._T_stop - 1):
            local_time = time - s * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= stop_var)

    # Startup ramp constraints - eq. (17)
    if thermal_unit._T_start >= 2:
        for s in range(1, thermal_unit._T_start):
            local_time = time - s * parameters.timestep
            turned_on_local_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_on_local_var <= start_var)

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

    # Relaxed reserve disabling condition - eq. (43)
    model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_flat_var - on_down_var))

    # Reserve availability constraints - eq. (44)
    # No reserves during OFF, START, or STOP states
    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var - stop_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var - stop_var))
    # Manual reserves only available in FLAT state
    model.add_constraint(reserves_up_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var - stop_var))
    model.add_constraint(reserves_down_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var - stop_var))

    # Power output bounds with all ramping capabilities - eq. (29) and (30)
    # Lower bound with shutdown ramping
    model.add_constraint(
        power_level_var >= q_lower * (on_up_var + on_down_var + on_flat_var) + turned_off_var * (q_min - q_step_down)
    )
    # Upper bound with both startup and shutdown ramping
    model.add_constraint(
        power_level_var
        <= q_upper * (on_up_var + on_down_var + on_flat_var)
        + (stop_var + start_var) * q_min
        - turned_off_var * q_step_down
    )

    # Power gradients with all auxiliary variables - most complex gradient logic
    if time in parameters.thermal_op_times[:-1]:  # Not the last time step
        if thermal_unit._Delta_Q > 0:  # Finite gradient
            # Upward gradient - eq. (33)
            model.add_constraint(
                power_level_var - power_prev_var
                <= thermal_unit._Delta_Q * entered_up_var
                + up_grad_prev_var
                + down_grad_prev_var
                - turned_off_var * q_step_down
                - stop_prev_var * q_step_down
                + turned_on_var * q_step_up
                + start_prev_var * q_step_up
                - dd_grad_prev_var
            )
            # Downward gradient - eq. (35)
            model.add_constraint(
                power_level_var - power_prev_var
                >= -thermal_unit._Delta_Q * entered_down_var
                + up_grad_prev_var
                + down_grad_prev_var
                - turned_off_var * q_step_down
                - stop_prev_var * q_step_down
                + flat_down_stop_var * thermal_unit._Delta_Q
                - dd_grad_prev_var
                + turned_on_var * q_step_up
                + start_prev_var * q_step_up
            )
        elif thermal_unit._Delta_Q == 0:  # Infinite gradient
            # Upward unconstrained gradient - eq. (34)
            model.add_constraint(
                power_level_var - power_prev_var
                <= thermal_unit._Delta_Q_unconstrained * entered_up_var
                + up_grad_prev_var
                + down_grad_prev_var
                - turned_off_var * q_step_down
                - stop_prev_var * q_step_down
                + turned_on_var * q_step_up
                + start_prev_var * q_step_up
                - dd_grad_prev_var
            )
            # Downward unconstrained gradient - eq. (36)
            model.add_constraint(
                power_level_var - power_prev_var
                >= -thermal_unit._Delta_Q_unconstrained * entered_down_var
                + up_grad_prev_var
                + down_grad_prev_var
                - turned_off_var * q_step_down
                - stop_prev_var * q_step_down
                + flat_down_stop_var * thermal_unit._Delta_Q_unconstrained
                - dd_grad_prev_var
                + turned_on_var * q_step_up
                + start_prev_var * q_step_up
            )

    # Daily energy constraints (if applicable)
    if thermal_unit.has_daily_energy_constraint:
        # This would need to be implemented at a higher level since it requires all time steps for a day
        pass
