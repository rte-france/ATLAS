"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal unit initial conditions - Combination 7: T_stop=False, T_start=True, T_stable=True
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

from atlas.math.timeseries import Timeseries

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO

from atlas.modules.portfolio_optimisation.models.thermal.initial_conditions_utils import (
    initialize_day_zero_core,
    initialize_day_zero_down_to_stop,
    initialize_day_zero_on_states,
    initialize_day_zero_start_state,
    initialize_day_zero_stop_state,
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
    """Combination 7: T_stop=False, T_start=True, T_stable=True"""
    if day_zero:
        # DayZero case: All units start OFF
        initialize_day_zero_core(thermal_unit, model, current_time)
        initialize_day_zero_on_states(thermal_unit, model, current_time)
        initialize_day_zero_stop_state(thermal_unit, model, current_time)
        initialize_day_zero_start_state(thermal_unit, model, current_time)
        initialize_day_zero_down_to_stop(thermal_unit, model, current_time)
    else:
        # Non-dayZero case: Initialize based on power history
        if current_time in power_timeseries.index:
            last_power = power_timeseries.get_value(current_time)
            min_power = thermal_unit.minimum_power.get_value(current_time)

            # Get variables
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{current_time}")
            stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{current_time}")
            start_var = model.get_variable(f"ON_START_{thermal_unit.name}_{current_time}")
            on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{current_time}")
            on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{current_time}")
            turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{current_time}")
            turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{current_time}")
            down_to_stop_var = model.get_variable(f"down_to_stop_grad_{current_time}_{thermal_unit.name}")
            power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{current_time}")

            # Fix power level to historical value
            model.add_constraint(power_level_var == last_power, f"init_power_{thermal_unit.name}_{current_time}")

            # Set state variables based on power level relative to minimum power
            if last_power >= min_power:
                # Unit is ON and above minimum power (normal operation)
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{current_time}")
                model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")
                model.add_constraint(start_var == 0, f"init_start_{thermal_unit.name}_{current_time}")
                # Set both ON states to 1 to allow flexibility (no stable constraints)
                model.add_constraint(on_down_var == 1, f"init_on_down_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_up_var == 1, f"init_on_up_{thermal_unit.name}_{current_time}")
            elif last_power > 0:
                # Unit is ON but below minimum power (startup or shutdown phase)
                # Initially set both START and STOP to 1, distinguish later based on trend
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{current_time}")
                model.add_constraint(stop_var == 1, f"init_stop_{thermal_unit.name}_{current_time}")
                model.add_constraint(start_var == 1, f"init_start_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")
            else:
                # Unit is completely OFF
                model.add_constraint(off_var == 1, f"init_off_{thermal_unit.name}_{current_time}")
                model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")
                model.add_constraint(start_var == 0, f"init_start_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")

            # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
            model.add_constraint(turned_on_var == 0, f"init_turned_on_{thermal_unit.name}_{current_time}")
            model.add_constraint(turned_off_var == 0, f"init_turned_off_{thermal_unit.name}_{current_time}")
            model.add_constraint(down_to_stop_var == 0, f"init_down_to_stop_{thermal_unit.name}_{current_time}")

            # Distinguish between startup and shutdown for intermediate power levels
            if current_time != extended_start_date and 0 < last_power < min_power:
                prev_time = current_time - parameters.timestep
                if prev_time in power_timeseries.index:
                    prev_power = power_timeseries.get_value(prev_time)

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
                if prev_time in power_timeseries.index:
                    prev_power = power_timeseries.get_value(prev_time)
                    prev_min_power = thermal_unit.minimum_power.get_value(prev_time)

                    # Detect turn off: entering STOP state
                    if prev_power >= prev_min_power and 0 < last_power < min_power and last_power < prev_power:
                        model.add_constraint(turned_off_var == 1, f"init_turned_off_{thermal_unit.name}_{current_time}")

                    # Detect turn on: entering START state
                    elif prev_power == 0 and last_power > 0:
                        model.add_constraint(turned_on_var == 1, f"init_turned_on_{thermal_unit.name}_{current_time}")

                    # Detect down_to_stop transition
                    # This occurs when unit goes from ON_DOWN to STOP
                    if (
                        0 < last_power < min_power  # Currently in STOP
                        and prev_power >= prev_min_power
                        and last_power < prev_power
                    ):  # Previously operational and decreasing
                        model.add_constraint(
                            down_to_stop_var == 1, f"init_down_to_stop_{thermal_unit.name}_{current_time}"
                        )


def add_constraints(
    thermal_unit: ThermalPO, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
) -> None:
    """Add constraints for Combination 7: T_start >= 1, T_stable >= 1, T_stop = 0

    This combination represents the scenario where:
    - T_start >= 1: Minimum start time requirement (startup sequence)
    - T_stable >= 1: Minimum stable operation time requirement
    - T_stop = 0: No minimum stop time requirement

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
    start_var = model.get_variable(f"ON_START_{thermal_unit.name}_{time}")
    stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{time}")
    turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{time}")
    turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{time}")
    down_to_stop_var = model.get_variable(f"down_to_stop_grad_{time}_{thermal_unit.name}")
    power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{time}")

    # Previous time variables
    off_prev_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{prev_time}")
    on_up_prev_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{prev_time}")
    on_down_prev_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{prev_time}")
    start_prev_var = model.get_variable(f"ON_START_{thermal_unit.name}_{prev_time}")
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

    # Constraints on down_to_stop - eq. (20)
    # Detects ON_DOWN(t-1) -> STOP(t) transition
    model.add_constraint(down_to_stop_var <= stop_var)
    model.add_constraint(down_to_stop_var <= on_down_prev_var)
    model.add_constraint(down_to_stop_var >= stop_var + on_down_prev_var - 1)

    # B. CONSTRAINTS ON THE STATE VARIABLES

    # Mutual exclusion constraint - 5 states - eq. (11)
    model.add_constraint(off_var + on_up_var + on_down_var + stop_var + start_var == 1)

    # Complex transition constraints
    # STOP to ON transitions are forbidden - eq. (15)
    model.add_constraint(stop_prev_var + on_up_var <= 1)
    model.add_constraint(stop_prev_var + on_down_var <= 1)

    # OFF to STOP transition is forbidden - eq. (14)
    model.add_constraint(off_prev_var + stop_var <= 1)

    # ON to OFF transitions are forbidden - eq. (19)
    model.add_constraint(on_up_prev_var + off_var <= 1)
    model.add_constraint(on_down_prev_var + off_var <= 1)

    # ON to START transitions are forbidden - eq. (12)
    model.add_constraint(on_up_prev_var + start_var <= 1)
    model.add_constraint(on_down_prev_var + start_var <= 1)

    # START to OFF transition is forbidden - eq. (13)
    model.add_constraint(start_prev_var + off_var <= 1)

    # START to STOP and STOP to START transitions are forbidden - eq. (16)
    model.add_constraint(start_prev_var + stop_var <= 1)
    model.add_constraint(stop_prev_var + start_var <= 1)

    # Direct OFF to ON transitions are forbidden - eq. (17)
    model.add_constraint(off_prev_var + on_up_var <= 1)
    model.add_constraint(off_prev_var + on_down_var <= 1)

    # Eviction constraints
    # START eviction - forces unit to leave START state after T_start time steps - eq. (16)
    if thermal_unit._T_start >= 1:
        start_eviction_time = time - (thermal_unit._T_start - 1) * parameters.timestep
        turned_on_start_eviction_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{start_eviction_time}")
        model.add_constraint(turned_on_start_eviction_var + start_var <= 1)

    # STOP eviction - forces unit to leave STOP state after T_stop time steps - eq. (19)
    if thermal_unit._T_stop > 1:
        stop_eviction_time = time - (thermal_unit._T_stop - 1) * parameters.timestep
        turned_off_stop_eviction_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{stop_eviction_time}")
        model.add_constraint(turned_off_stop_eviction_var + stop_var <= 1)

    # Minimum time constraints
    if thermal_unit._T_on >= 2:
        for s in range(1, thermal_unit._T_on):
            # eq. (27) with T_start > 0 - adjusted timing for startup
            local_time = time - (s + thermal_unit._T_start) * parameters.timestep
            turned_on_local_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

    if thermal_unit._T_off >= 2:
        for s in range(1, thermal_unit._T_off):
            # eq. (28) with T_stop > 0 - adjusted timing for shutdown
            local_time = time - (s + thermal_unit._T_stop) * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= off_var)

    # Shutdown ramp constraints - eq. (19)
    if thermal_unit._T_stop >= 2:
        for s in range(1, thermal_unit._T_stop - 1):
            local_time = time - s * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= stop_var)

    # Startup ramp constraints - eq. (18)
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
    model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_down_var))

    # Reserve availability constraints - eq. (44)
    # No reserves during OFF, START, or STOP states
    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var - stop_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var - stop_var))
    model.add_constraint(reserves_up_var <= q_upper * (1 - off_var - start_var - stop_var))
    model.add_constraint(reserves_down_var <= q_upper * (1 - off_var - start_var - stop_var))

    # Power output bounds with dual gradient ramping - eq. (29) and (30)
    # Lower bound with shutdown ramping
    model.add_constraint(
        power_level_var >= q_lower * (on_up_var + on_down_var) + turned_off_var * (q_min - q_step_down)
    )
    # Upper bound with both startup and shutdown ramping
    model.add_constraint(
        power_level_var
        <= q_upper * (on_up_var + on_down_var) + stop_var * q_min + start_var * q_min - turned_off_var * q_step_down
    )

    # Power gradients with dual gradient parameters
    if time in parameters.thermal_op_times[:-1]:  # Not the last time step
        if thermal_unit._Delta_Q > 0:  # Finite gradient
            # Upward gradient - eq. (33)
            model.add_constraint(
                power_level_var - power_prev_var
                <= thermal_unit._Delta_Q * on_up_prev_var
                - turned_off_var * q_step_down
                - stop_prev_var * q_step_down
                + turned_on_var * q_step_up
                + start_prev_var * q_step_up
            )
            # Downward gradient - eq. (35)
            model.add_constraint(
                power_level_var - power_prev_var
                >= -thermal_unit._Delta_Q * on_down_prev_var
                - turned_off_var * q_step_down
                - stop_prev_var * q_step_down
                + down_to_stop_var * thermal_unit._Delta_Q
                + turned_on_var * q_step_up
                + start_prev_var * q_step_up
            )
        elif thermal_unit._Delta_Q == 0:  # Infinite gradient
            # Upward unconstrained gradient - eq. (34)
            model.add_constraint(
                power_level_var - power_prev_var
                <= thermal_unit._Delta_Q_unconstrained * on_up_prev_var
                - turned_off_var * q_step_down
                - stop_prev_var * q_step_down
                + turned_on_var * q_step_up
                + start_prev_var * q_step_up
            )
            # Downward unconstrained gradient - eq. (36)
            model.add_constraint(
                power_level_var - power_prev_var
                >= -thermal_unit._Delta_Q_unconstrained * on_down_prev_var
                - turned_off_var * q_step_down
                - stop_prev_var * q_step_down
                + down_to_stop_var * thermal_unit._Delta_Q_unconstrained
                + turned_on_var * q_step_up
                + start_prev_var * q_step_up
            )

    # Daily energy constraints (if applicable)
    if thermal_unit.has_daily_energy_constraint:
        # This would need to be implemented at a higher level since it requires all time steps for a day
        pass
