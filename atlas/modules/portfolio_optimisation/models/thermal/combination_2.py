"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal unit combination 2: T_stop >= 1, T_stable = T_start = 0
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
    """Combination 2: T_stop=True, T_start=False, T_stable=False"""

    if day_zero:
        # DayZero case: All units start OFF
        # Get state variables
        off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{current_time}")
        on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{current_time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{current_time}")
        stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{current_time}")
        turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{current_time}")
        turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{current_time}")
        down_to_stop_var = model.get_variable(f"down_to_stop_grad_{current_time}_{thermal_unit.name}")
        power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{current_time}")

        # Fix state variables using equality constraints
        model.add_constraint(off_var == 1, f"init_off_{thermal_unit.name}_{current_time}")
        model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
        model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")
        model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")

        # Fix auxiliary variables
        model.add_constraint(turned_on_var == 0, f"init_turned_on_{thermal_unit.name}_{current_time}")
        model.add_constraint(turned_off_var == 0, f"init_turned_off_{thermal_unit.name}_{current_time}")
        model.add_constraint(down_to_stop_var == 0, f"init_down_to_stop_{thermal_unit.name}_{current_time}")

        # Fix power level to 0
        model.add_constraint(power_level_var == 0, f"init_power_{thermal_unit.name}_{current_time}")
    else:
        # Non-dayZero case: Initialize based on power history
        if current_time in power_history.index:
            last_power = power_history.get_value(current_time)
            min_power = thermal_unit.minimum_power.get_value(current_time)

            # Get variables
            off_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{current_time}")
            on_up_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{current_time}")
            on_down_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{current_time}")
            stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{current_time}")
            turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{current_time}")
            turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{current_time}")
            down_to_stop_var = model.get_variable(f"down_to_stop_grad_{current_time}_{thermal_unit.name}")
            power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{current_time}")

            # Fix power level to historical value
            model.add_constraint(power_level_var == last_power, f"init_power_{thermal_unit.name}_{current_time}")

            # Set state variables based on power level relative to minimum power
            if last_power >= min_power:
                # Unit is ON and above minimum power
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{current_time}")
                model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_up_var == 1, f"init_on_up_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_down_var == 1, f"init_on_down_{thermal_unit.name}_{current_time}")
            elif last_power > 0:
                # Unit is ON but below minimum power (in shutdown phase)
                model.add_constraint(off_var == 0, f"init_off_{thermal_unit.name}_{current_time}")
                model.add_constraint(stop_var == 1, f"init_stop_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")
            else:
                # Unit is completely OFF
                model.add_constraint(off_var == 1, f"init_off_{thermal_unit.name}_{current_time}")
                model.add_constraint(stop_var == 0, f"init_stop_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{thermal_unit.name}_{current_time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{thermal_unit.name}_{current_time}")

            # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
            model.add_constraint(turned_on_var == 0, f"init_turned_on_{thermal_unit.name}_{current_time}")
            model.add_constraint(turned_off_var == 0, f"init_turned_off_{thermal_unit.name}_{current_time}")
            model.add_constraint(down_to_stop_var == 0, f"init_down_to_stop_{thermal_unit.name}_{current_time}")

            # Reconstruct transitions for non-initial times
            if current_time != extended_start_date:
                prev_time = current_time - parameters.timestep
                if prev_time in power_history.index:
                    prev_power = power_history.get_value(prev_time)

                    # Detect transitions based on state changes
                    # Turn off: entering STOP state
                    if prev_power >= min_power and 0 < last_power < min_power:
                        model.add_constraint(turned_off_var == 1, f"init_turned_off_{thermal_unit.name}_{current_time}")

                    # Turn on: exiting OFF state
                    elif prev_power == 0 and last_power > 0:
                        model.add_constraint(turned_on_var == 1, f"init_turned_on_{thermal_unit.name}_{current_time}")

                    # Transition from ON_DOWN to STOP (down_to_stop)
                    elif prev_power > min_power and 0 < last_power < min_power:
                        model.add_constraint(
                            down_to_stop_var == 1, f"init_down_to_stop_{thermal_unit.name}_{current_time}"
                        )


def add_constraints(
    thermal_unit: ThermalPO, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
) -> None:
    """Add constraints for Combination 2: T_stop >= 1, T_stable = T_start = 0

    This combination represents the scenario where:
    - T_stop >= 1: Minimum stop time requirement (shutdown sequence)
    - T_stable = 0: No stable operation time requirement
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
    stop_var = model.get_variable(f"STOP_{thermal_unit.name}_{time}")
    turned_on_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{time}")
    turned_off_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{time}")
    down_to_stop_var = model.get_variable(f"down_to_stop_grad_{time}_{thermal_unit.name}")
    power_level_var = model.get_variable(f"{thermal_unit.name}_power_level_{time}")

    # Previous time variables
    off_prev_var = model.get_variable(f"OFF_var_{thermal_unit.name}_{prev_time}")
    on_up_prev_var = model.get_variable(f"ON_UP_var_{thermal_unit.name}_{prev_time}")
    on_down_prev_var = model.get_variable(f"ON_DOWN_var_{thermal_unit.name}_{prev_time}")
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

    # Power bounds and parameters
    q_upper = thermal_unit.maximum_power.get_value(time)
    q_lower = thermal_unit.minimum_power.get_value(time)
    maximum_automated = get_maximum_automated(thermal_unit)

    # Shutdown gradient parameters
    q_min = thermal_unit.minimum_power.max()  # Get the minimum power without reserve requirements
    q_step = q_min / thermal_unit._T_stop

    # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

    # Constraints on turned_on (sec. 6.1.1)
    model.add_constraint(turned_on_var <= 1 - off_var)
    model.add_constraint(turned_on_var <= off_prev_var)
    model.add_constraint(turned_on_var >= off_prev_var - off_var)

    # Constraints on turned_off (sec. 6.1.2) - when entering STOP state
    model.add_constraint(turned_off_var <= 1 - stop_prev_var)
    model.add_constraint(turned_off_var <= stop_var)
    model.add_constraint(turned_off_var >= stop_var - stop_prev_var)

    # Constraints on down_to_stop (sec. 6.1.5)
    model.add_constraint(down_to_stop_var <= 1 - on_down_prev_var)
    model.add_constraint(down_to_stop_var <= on_down_var)
    model.add_constraint(down_to_stop_var >= on_down_var - on_down_prev_var)

    # B. CONSTRAINTS ON THE STATE VARIABLES

    # Mutual exclusion constraint - now includes STOP state
    model.add_constraint(off_var + on_up_var + on_down_var + stop_var == 1)

    # Transition constraints
    # Forbidden transitions: OFF->STOP, STOP->ON_UP/ON_DOWN, ON_UP/ON_DOWN->OFF
    model.add_constraint(stop_prev_var + on_up_var <= 1)
    model.add_constraint(stop_prev_var + on_down_var <= 1)
    model.add_constraint(off_prev_var + stop_var <= 1)
    model.add_constraint(on_up_prev_var + off_var <= 1)
    model.add_constraint(on_down_prev_var + off_var <= 1)

    # Eviction constraint (equation 19)
    if thermal_unit._T_stop > 1:
        eviction_time = time - (thermal_unit._T_stop - 1) * parameters.timestep
        turned_off_eviction_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{eviction_time}")
        model.add_constraint(turned_off_eviction_var + stop_var <= 1)

    # Minimum time constraints
    if thermal_unit._T_on >= 2:
        for s in range(1, thermal_unit._T_on):
            local_time = time - s * parameters.timestep
            turned_on_local_var = model.get_variable(f"t_on_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

    if thermal_unit._T_off >= 2:
        for s in range(1, thermal_unit._T_off):
            local_time = time - (s + thermal_unit._T_stop) * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= off_var)

    # Shutdown ramp constraints
    if thermal_unit._T_stop >= 2:
        for s in range(1, thermal_unit._T_stop - 1):
            local_time = time - s * parameters.timestep
            turned_off_local_var = model.get_variable(f"t_off_of_{thermal_unit.name}_{local_time}")
            model.add_constraint(turned_off_local_var <= stop_var)

    # C. CONSTRAINTS ON THE CONTROL VARIABLE

    # Reserve "fill up" constraints (same as Combination 1)
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

    # Relaxed reserve disabling condition
    model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_down_var))

    # Reserve availability constraints - now includes STOP state
    model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - stop_var))
    model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - stop_var))
    model.add_constraint(reserves_up_var <= q_upper * (1 - off_var - stop_var))
    model.add_constraint(reserves_down_var <= q_upper * (1 - off_var - stop_var))

    # Power output bounds with shutdown gradient
    model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var) + turned_off_var * (q_min - q_step))
    model.add_constraint(
        power_level_var <= q_upper * (on_up_var + on_down_var) + stop_var * q_min - turned_off_var * q_step
    )

    # Power gradients with shutdown considerations
    if time in parameters.thermal_op_times[:-1]:  # Not the last time step
        if thermal_unit._Delta_Q > 0:  # Finite gradient
            # Upward gradient
            model.add_constraint(
                power_level_var - power_prev_var
                <= thermal_unit._Delta_Q * on_up_prev_var
                - turned_off_var * q_step
                - stop_prev_var * q_step
                + thermal_unit._Delta_Q_unconstrained * turned_on_var
            )
            # Downward gradient
            model.add_constraint(
                power_level_var - power_prev_var
                >= -thermal_unit._Delta_Q * on_down_prev_var
                - turned_off_var * q_step
                - stop_prev_var * q_step
                + down_to_stop_var * thermal_unit._Delta_Q
            )
        elif thermal_unit._Delta_Q == 0:  # Infinite gradient
            model.add_constraint(
                power_level_var - power_prev_var
                <= thermal_unit._Delta_Q_unconstrained * on_up_prev_var
                - turned_off_var * q_step
                - stop_prev_var * q_step
                + thermal_unit._Delta_Q_unconstrained * turned_on_var
            )
            model.add_constraint(
                power_level_var - power_prev_var
                >= -thermal_unit._Delta_Q_unconstrained * on_down_prev_var
                - turned_off_var * q_step
                - stop_prev_var * q_step
                + thermal_unit._Delta_Q_unconstrained * down_to_stop_var
            )

    # Daily energy constraints (if applicable)
    if thermal_unit.has_daily_energy_constraint:
        # This would need to be implemented at a higher level since it requires all time steps for a day
        pass
