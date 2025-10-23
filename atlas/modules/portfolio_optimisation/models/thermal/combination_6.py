"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal unit combination 6: T_stop >= 1, T_stable >= 1, T_start = 0
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
    initialize_day_zero_start_state,
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
    """Combination 6: T_stop=0, T_start>=1, T_stable>=1"""
    if day_zero:
        for time in kwargs.get("initial_times", []):
            initialize_day_zero_core(thermal_unit, model, time)
            initialize_day_zero_gradient_vars(thermal_unit, model, time)
            initialize_day_zero_start_state(thermal_unit, model, time)

        for time in kwargs.get("stable_initial_times", []):
            initialize_day_zero_stable_vars(thermal_unit, model, time)

    else:
        # Non-dayZero case: Initialize based on power history
        for time in kwargs.get("initial_times", []):
            last_power = power_timeseries.get_value(time)
            min_power = thermal_unit.minimum_power.get_value(time)

            # Get variables
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{time}")
            start_var = model.get_variable(f"ON_START_{thermal_unit.name}_{time}")
            turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{time}")
            turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{time}")

            # Set state variables based on power level relative to minimum power
            if last_power >= min_power:
                # Unit is ON and above minimum power
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{time}")
                model.add_constraint(start_var == 0, f"init_start_{thermal_unit.name}_{time}")
            elif last_power > 0:
                # Unit is ON but below minimum power (in startup phase)
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{time}")
                model.add_constraint(start_var == 1, f"init_start_{thermal_unit.name}_{time}")
            else:
                # Unit is completely OFF
                model.add_constraint(off_var == 1, f"init_off_{thermal_unit.name}_{time}")
                model.add_constraint(start_var == 0, f"init_start_{thermal_unit.name}_{time}")

            # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
            model.add_constraint(turned_on_var == 0, f"init_turned_on_{thermal_unit.name}_{time}")
            model.add_constraint(turned_off_var == 0, f"init_turned_off_{thermal_unit.name}_{time}")

            # Reconstruct transitions for non-initial times
            if time != extended_start_date:
                prev_time = time - parameters.timestep

                # Detect turn off: unit goes to OFF state
                if (
                    model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{time}").lower_bound
                    - model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{prev_time}").lower_bound
                    == 1
                ):
                    model.add_constraint(turned_off_var == 1, f"init_turned_off_{thermal_unit.name}_{time}")

                # Detect turn on: unit enters START state (from OFF to startup)
                elif (
                    model.get_constraint_bounds(f"init_start_{thermal_unit.name}_{time}").lower_bound
                    - model.get_constraint_bounds(f"init_start_{thermal_unit.name}_{prev_time}").lower_bound
                    == 1
                ):
                    model.add_constraint(turned_on_var == 1, f"init_turned_off_{thermal_unit.name}_{time}")

        for time in kwargs.get("stable_initial_times", []):
            current_power = power_timeseries.get_value(time)
            next_power = power_timeseries.get_value(time + parameters.timestep)
            min_power = thermal_unit.minimum_power.get_value(time)

            # Get stable state variables
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{time}")
            start_var = model.get_variable(f"ON_START_{thermal_unit.name}_{time}")
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

            # Set stable state variables based on unit state
            if model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{time}").lower_bound == 0:
                if model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{time}").lower_bound == 1:
                    model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{time}")
                    model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{time}")
                    model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{time}")

                else:
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

            else:
                # Unit is in START state - no UP/DOWN/FLAT allowed
                model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{time}")
                model.add_constraint(on_flat_var == 0, f"init_on_flat_{thermal_unit.name}_{time}")

                # Detect state transitions for non-initial times
                if (
                    time != extended_start_date
                    and model.get_constraint_bounds(f"init_off_{thermal_unit.name}_{time}").lower_bound == 1
                ):
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
    """Add constraints for Combination 6: T_stop >= 1, T_stable >= 1, T_start = 0

    This combination represents the scenario where:
    - T_stop >= 1: Minimum stop time requirement (shutdown sequence)
    - T_stable >= 1: Minimum stable operation time requirement
    - T_start = 0: No minimum start time requirement

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
    stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{time}")
    turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{time}")
    turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{time}")
    stable_var = model.get_variable(f"stable_{time}_{thermal_unit.name}")
    entered_up_var = model.get_variable(f"entered_up_{time}_{thermal_unit.name}")
    entered_down_var = model.get_variable(f"entered_down_{time}_{thermal_unit.name}")
    power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{time}")

    # Previous time variables
    off_prev_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{prev_time}")
    on_up_prev_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{prev_time}")
    on_down_prev_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{prev_time}")
    on_flat_prev_var = model.get_variable(f"ON_FLAT_{thermal_unit.name}_{prev_time}")
    stop_prev_var = model.get_variable(f"STOP_{thermal_unit.name}_{prev_time}")
    power_prev_var = model.get_variable(f"{thermal_unit.name}_power_level_{prev_time}")

    # Reserve variables
    reserves_up_var = model.get_variable(f"reserves_up_{thermal_unit.name}_{time}")
    reserves_down_var = model.get_variable(f"reserves_down_{thermal_unit.name}_{time}")
    automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{thermal_unit.name}_{time}")
    automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{thermal_unit.name}_{time}")
    unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{thermal_unit.name}_{time}")
    unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{thermal_unit.name}_{time}")
    relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{thermal_unit.name}_{time}")

    # Power bounds and shutdown parameters
    q_upper = thermal_unit.maximum_power.get_value(time)
    q_lower = thermal_unit.minimum_power.get_value(time)
    maximum_automated = get_maximum_automated(thermal_unit)

    # Shutdown gradient parameters
    q_min = thermal_unit.minimum_power.max()
    q_step = q_min / thermal_unit._T_stop

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

    # Constraints on entered_up - eq. (7)
    model.add_constraint(entered_up_var <= 1 - on_up_prev_var)
    model.add_constraint(entered_up_var <= on_up_var)
    model.add_constraint(entered_up_var >= on_up_var - on_up_prev_var)

    # Constraints on entered_down - eq. (8)
    model.add_constraint(entered_down_var <= 1 - on_down_prev_var)
    model.add_constraint(entered_down_var <= on_down_var)
    model.add_constraint(entered_down_var >= on_down_var - on_down_prev_var)

    # B. CONSTRAINTS ON THE STATE VARIABLES

    # Mutual exclusion constraint - 5 states - eq. (9)
    model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var + stop_var == 1)

    # Transition constraints - eq. (25)
    # UP-DOWN and DOWN-UP transitions are forbidden
    model.add_constraint(on_up_prev_var + on_down_var <= 1)
    model.add_constraint(on_down_prev_var + on_up_var <= 1)
    # ON_XX to OFF transitions are forbidden (must go through STOP)
    model.add_constraint(on_up_prev_var + off_var <= 1)
    model.add_constraint(on_down_prev_var + off_var <= 1)
    model.add_constraint(on_flat_prev_var + off_var <= 1)

    # STOP to ON transitions are forbidden - eq. (13)
    model.add_constraint(stop_prev_var + on_flat_var <= 1)
    model.add_constraint(stop_prev_var + on_down_var <= 1)
    model.add_constraint(stop_prev_var + on_up_var <= 1)

    # ON_UP to STOP transition is forbidden - eq. (21)
    model.add_constraint(on_up_prev_var + stop_var <= 1)
    # OFF to STOP transition is forbidden - eq. (12)
    model.add_constraint(off_prev_var + stop_var <= 1)

    # Eviction constraint - unit must leave STOP state after T_stop time steps - eq. (19)
    if thermal_unit._T_stop > 1:
        eviction_time = time - (thermal_unit._T_stop - 1) * parameters.timestep
        turned_off_eviction_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{eviction_time}")
        model.add_constraint(turned_off_eviction_var + stop_var <= 1)

    # Minimum time constraints
    if thermal_unit._T_on >= 2:
        for s in range(1, thermal_unit._T_on):
            local_time = time - s * parameters.timestep
            turned_on_local_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

    if thermal_unit._T_off >= 2:
        for s in range(1, thermal_unit._T_off):
            local_time = time - (s + thermal_unit._T_stop) * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= off_var)

    if thermal_unit._T_stable >= 2:
        for s in range(1, thermal_unit._T_stable - 1):
            local_time = time - s * parameters.timestep
            stable_local_var = model.get_variable(f"stable_{local_time}_{thermal_unit.name}")
            model.add_constraint(stable_local_var <= on_flat_var)

    # Shutdown ramp constraints - eq. (24)
    if thermal_unit._T_stop >= 2:
        for s in range(1, thermal_unit._T_stop - 1):
            local_time = time - s * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= stop_var)

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
    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - stop_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - stop_var))
    # Manual reserves only available in FLAT state (not during ramping)
    model.add_constraint(reserves_up_var <= q_upper * (1 - on_up_var - on_down_var - off_var - stop_var))
    model.add_constraint(reserves_down_var <= q_upper * (1 - on_up_var - on_down_var - off_var - stop_var))

    # Power output bounds with shutdown gradient
    # Lower bound with shutdown ramping
    model.add_constraint(
        power_level_var >= q_lower * (on_up_var + on_down_var + on_flat_var) + turned_off_var * (q_min - q_step)
    )
    # Upper bound with shutdown ramping
    model.add_constraint(
        power_level_var
        <= q_upper * (on_up_var + on_down_var + on_flat_var) + stop_var * q_min - turned_off_var * q_step
    )

    # Daily energy constraints (if applicable)
    if thermal_unit.has_daily_energy_constraint:
        # This would need to be implemented at a higher level since it requires all time steps for a day
        pass
