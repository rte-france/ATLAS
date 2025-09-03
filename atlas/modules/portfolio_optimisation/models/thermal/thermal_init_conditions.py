"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Thermal unit initial condition combinations for different constraint scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

from atlas.math.timeseries import Timeseries

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.models.thermal.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.solver_interface import OptimisationModel


class ThermalInitialConditions:
    """Handles initial conditions for thermal units across 8 different combinations."""

    def __init__(self, thermal_unit: ThermalPO):
        """Initialize with reference to the thermal unit."""
        self.thermal_unit = thermal_unit

    def add_combination_1_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        initial_times: list[DateTime],
        extended_start_date: DateTime,
        power_history: Timeseries | None,
        day_zero: bool,
    ) -> None:
        """Combination 1: T_stop=False, T_start=False, T_stable=False"""
        if day_zero:
            # DayZero case: All units start OFF
            for time in initial_times:
                # Get state variables
                off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                # Fix state variables using equality constraints
                model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(power_level_var == 0, f"init_power_{self.thermal_unit.name}_{time}")
        else:
            # Non-dayZero case: Initialize based on power history
            for time in initial_times:
                if time in power_history.time_index:
                    last_power = power_history.get_value(time)
                    min_power = self.thermal_unit.minimum_power.get_value(time)

                    # Get variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                    on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                    turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                    turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                    power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                    # Fix power level to historical value
                    model.add_constraint(power_level_var == last_power, f"init_power_{self.thermal_unit.name}_{time}")

                    # Set state variables based on power level
                    if last_power >= min_power:
                        # Unit is ON and producing at or above minimum power
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        # Note: ON_UP/ON_DOWN/ON_FLAT will be determined by power trend analysis
                    elif last_power > 0:
                        # Unit is ON but below minimum power (could be starting or stopping)
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is completely OFF
                        model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")

                    # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
                    model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                    model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")

                    # Reconstruct transitions for non-initial times
                    if time != extended_start_date:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)

                            # Detect turn off: units going from ON to OFF
                            if prev_power > 0 and last_power == 0:
                                model.add_constraint(
                                    turned_off_var == 1, f"init_turned_off_{self.thermal_unit.name}_{time}"
                                )

                            # Detect turn on: units going from OFF to ON
                            elif prev_power == 0 and last_power > 0:
                                model.add_constraint(
                                    turned_on_var == 1, f"init_turned_on_{self.thermal_unit.name}_{time}"
                                )

    def add_combination_2_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        initial_times: list[DateTime],
        extended_start_date: DateTime,
        power_history: Timeseries | None,
        day_zero: bool,
    ) -> None:
        """Combination 2: T_stop=True, T_start=False, T_stable=False"""

        if day_zero:
            # DayZero case: All units start OFF
            for time in initial_times:
                # Get state variables
                off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                down_to_stop_var = model.get_variable(f"down_to_stop_grad_at_{time}_e_{self.thermal_unit.name}")
                power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                # Fix state variables using equality constraints
                model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")

                # Fix auxiliary variables
                model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(down_to_stop_var == 0, f"init_down_to_stop_{self.thermal_unit.name}_{time}")

                # Fix power level to 0
                model.add_constraint(power_level_var == 0, f"init_power_{self.thermal_unit.name}_{time}")
        else:
            # Non-dayZero case: Initialize based on power history
            for time in initial_times:
                if time in power_history.time_index:
                    last_power = power_history.get_value(time)
                    min_power = self.minimum_power.get_value(time)

                    # Get variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                    on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                    stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                    turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                    turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                    down_to_stop_var = model.get_variable(f"down_to_stop_grad_at_{time}_e_{self.thermal_unit.name}")
                    power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                    # Fix power level to historical value
                    model.add_constraint(power_level_var == last_power, f"init_power_{self.thermal_unit.name}_{time}")

                    # Set state variables based on power level relative to minimum power
                    if last_power >= min_power:
                        # Unit is ON and above minimum power
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 1, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 1, f"init_on_down_{self.thermal_unit.name}_{time}")
                    elif last_power > 0:
                        # Unit is ON but below minimum power (in shutdown phase)
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 1, f"init_stop_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is completely OFF
                        model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")

                    # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
                    model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                    model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")
                    model.add_constraint(down_to_stop_var == 0, f"init_down_to_stop_{self.thermal_unit.name}_{time}")

                    # Reconstruct transitions for non-initial times
                    if time != extended_start_date:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)

                            # Detect transitions based on state changes
                            # Turn off: entering STOP state
                            if prev_power >= min_power and 0 < last_power < min_power:
                                model.add_constraint(
                                    turned_off_var == 1, f"init_turned_off_{self.thermal_unit.name}_{time}"
                                )

                            # Turn on: exiting OFF state
                            elif prev_power == 0 and last_power > 0:
                                model.add_constraint(
                                    turned_on_var == 1, f"init_turned_on_{self.thermal_unit.name}_{time}"
                                )

                            # Transition from ON_DOWN to STOP (down_to_stop)
                            elif prev_power > min_power and 0 < last_power < min_power:
                                model.add_constraint(
                                    down_to_stop_var == 1, f"init_down_to_stop_{self.thermal_unit.name}_{time}"
                                )

    def add_combination_3_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        initial_times: list[DateTime],
        extended_start_date: DateTime,
        power_history: Timeseries | None,
        day_zero: bool,
    ) -> None:
        """Combination 3: T_stop=False, T_start=True, T_stable=False"""
        # Create stable initial condition time frame (excludes the last timestep)
        stable_initial_times = []
        if len(initial_times) > 1:
            stable_initial_times = initial_times[:-1]  # All except the last time step

        if day_zero:
            # DayZero case: All units start OFF
            for time in initial_times:
                # Get state variables
                off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                # Fix state variables using equality constraints
                model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")

                # Fix auxiliary variables
                model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")

                # Fix power level to 0
                model.add_constraint(power_level_var == 0, f"init_power_{self.thermal_unit.name}_{time}")

            # Initialize stable-specific variables for dayZero
            for time in stable_initial_times:
                # Get stable state variables
                on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
                on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
                entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
                entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")

                # Fix stable state variables
                model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")

                # Fix stable auxiliary variables
                model.add_constraint(stable_var == 0, f"init_stable_{self.thermal_unit.name}_{time}")
                model.add_constraint(entered_up_var == 0, f"init_entered_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(entered_down_var == 0, f"init_entered_down_{self.thermal_unit.name}_{time}")

            # Initialize gradient auxiliaries to 0 for dayZero
            for time in initial_times:
                u_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.thermal_unit.name}")
                d_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.thermal_unit.name}")
                tilde_u_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.thermal_unit.name}")
                tilde_d_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.thermal_unit.name}")

                model.add_constraint(u_var == 0, f"init_u_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(d_var == 0, f"init_d_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(tilde_u_var == 0, f"init_tilde_u_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(tilde_d_var == 0, f"init_tilde_d_grad_{self.thermal_unit.name}_{time}")

        else:
            # Non-dayZero case: Initialize based on power history
            for time in initial_times:
                if time in power_history.time_index:
                    last_power = power_history.get_value(time)

                    # Get variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                    turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                    power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                    # Fix power level to historical value
                    model.add_constraint(power_level_var == last_power, f"init_power_{self.thermal_unit.name}_{time}")

                    # Set OFF state based on power level
                    if last_power > 0:
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                    else:
                        model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")

                    # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
                    model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                    model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")

                    # Reconstruct transitions for non-initial times
                    if time != extended_start_date:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)

                            # Detect turn off: was ON -> now OFF
                            if prev_power > 0 and last_power == 0:
                                model.add_constraint(
                                    turned_off_var == 1, f"init_turned_off_{self.thermal_unit.name}_{time}"
                                )

                            # Detect turn on: was OFF -> now ON
                            elif prev_power == 0 and last_power > 0:
                                model.add_constraint(
                                    turned_on_var == 1, f"init_turned_on_{self.thermal_unit.name}_{time}"
                                )

            # Handle stable-specific variables for non-dayZero
            for time in stable_initial_times:
                if time in power_history.time_index:
                    current_power = power_history.get_value(time)
                    next_time = time + parameters.timestep
                    next_power = (
                        power_history.get_value(next_time) if next_time in power_history.time_index else current_power
                    )

                    # Get stable state variables
                    on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
                    on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                    on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                    stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
                    entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
                    entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")

                    # Initialize auxiliary variables to 0
                    model.add_constraint(stable_var == 0, f"init_stable_{self.thermal_unit.name}_{time}")
                    model.add_constraint(entered_up_var == 0, f"init_entered_up_{self.thermal_unit.name}_{time}")
                    model.add_constraint(entered_down_var == 0, f"init_entered_down_{self.thermal_unit.name}_{time}")

                    # Set stable state variables based on power trend (only if unit is ON)
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    if current_power > 0:
                        if current_power < next_power:
                            # Power is increasing
                            model.add_constraint(on_up_var == 1, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                        elif current_power > next_power:
                            # Power is decreasing
                            model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 1, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                        else:
                            # Power is stable
                            model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 1, f"init_on_flat_{self.thermal_unit.name}_{time}")

                        # Detect state transitions for non-initial times
                        if time != extended_start_date:
                            prev_time = time - parameters.timestep
                            if prev_time in power_history.time_index:
                                # Detect entering FLAT state
                                prev_next_time = prev_time + parameters.timestep
                                prev_power = power_history.get_value(prev_time)
                                prev_next_power = (
                                    power_history.get_value(prev_next_time)
                                    if prev_next_time in power_history.time_index
                                    else prev_power
                                )

                                prev_was_flat = prev_power == prev_next_power and prev_power > 0
                                current_is_flat = current_power == next_power and current_power > 0

                                if not prev_was_flat and current_is_flat:
                                    model.add_constraint(
                                        stable_var == 1, f"init_stable_{self.thermal_unit.name}_{time}"
                                    )

                                # Detect entering UP state
                                prev_was_up = prev_power < prev_next_power
                                current_is_up = current_power < next_power

                                if not prev_was_up and current_is_up:
                                    model.add_constraint(
                                        entered_up_var == 1, f"init_entered_up_{self.thermal_unit.name}_{time}"
                                    )

                                # Detect entering DOWN state
                                prev_was_down = prev_power > prev_next_power
                                current_is_down = current_power > next_power

                                if not prev_was_down and current_is_down:
                                    model.add_constraint(
                                        entered_down_var == 1, f"init_entered_down_{self.thermal_unit.name}_{time}"
                                    )

            # Initialize gradient auxiliaries for the last time step
            if len(initial_times) >= 2:
                start_date_minus_one = parameters.start_date - parameters.timestep
                start_date_minus_two = parameters.start_date - 2 * parameters.timestep

                if (
                    start_date_minus_one in power_history.time_index
                    and start_date_minus_two in power_history.time_index
                ):
                    power_minus_one = power_history.get_value(start_date_minus_one)
                    power_minus_two = power_history.get_value(start_date_minus_two)

                    # Get gradient auxiliary variables
                    u_var = model.get_variable(f"UP_grad_at_{start_date_minus_one}_for_e_{self.thermal_unit.name}")
                    d_var = model.get_variable(f"DOWN_grad_at_{start_date_minus_one}_e_{self.thermal_unit.name}")

                    # Calculate gradient values based on power trend
                    power_diff = power_minus_one - power_minus_two

                    # U gradient: only non-zero if unit was in UP state at both time steps
                    if power_minus_two > 0 and power_minus_one > 0 and power_minus_two < power_minus_one:
                        model.add_constraint(
                            u_var == power_diff, f"init_u_grad_{self.thermal_unit.name}_{start_date_minus_one}"
                        )
                    else:
                        model.add_constraint(u_var == 0, f"init_u_grad_{self.thermal_unit.name}_{start_date_minus_one}")

                    # D gradient: only non-zero if unit was in DOWN state at both time steps
                    if power_minus_two > 0 and power_minus_one > 0 and power_minus_two > power_minus_one:
                        model.add_constraint(
                            d_var == power_diff, f"init_d_grad_{self.thermal_unit.name}_{start_date_minus_one}"
                        )
                    else:
                        model.add_constraint(d_var == 0, f"init_d_grad_{self.thermal_unit.name}_{start_date_minus_one}")

    def add_combination_4_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        initial_times: list[DateTime],
        extended_start_date: DateTime,
        power_history: Timeseries | None,
        day_zero: bool,
    ) -> None:
        """Combination 4: T_stop=True, T_start=True, T_stable=False"""
        if day_zero:
            # DayZero case: All units start OFF
            for time in initial_times:
                # Get state variables
                off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                # Fix state variables using equality constraints
                model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")

                # Fix auxiliary variables
                model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")

                # Fix power level to 0
                model.add_constraint(power_level_var == 0, f"init_power_{self.thermal_unit.name}_{time}")
        else:
            # Non-dayZero case: Initialize based on power history
            for time in initial_times:
                if time in power_history.time_index:
                    last_power = power_history.get_value(time)
                    min_power = self.minimum_power.get_value(time)

                    # Get variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                    on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                    start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                    turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                    turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                    power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                    # Fix power level to historical value
                    model.add_constraint(power_level_var == last_power, f"init_power_{self.thermal_unit.name}_{time}")

                    # Set state variables based on power level relative to minimum power
                    if last_power >= min_power:
                        # Unit is ON and above minimum power (normal operation)
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 1, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 1, f"init_on_down_{self.thermal_unit.name}_{time}")
                    elif last_power > 0:
                        # Unit is ON but below minimum power (in startup phase)
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 1, f"init_start_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is completely OFF
                        model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")

                    # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
                    model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                    model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")

                    # Reconstruct transitions for non-initial times
                    if time != extended_start_date:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)

                            # Detect turn off: unit goes to OFF state
                            if prev_power > 0 and last_power == 0:
                                model.add_constraint(
                                    turned_off_var == 1, f"init_turned_off_{self.thermal_unit.name}_{time}"
                                )

                            # Detect turn on: unit enters START state (from OFF to startup)
                            elif prev_power == 0 and last_power > 0:
                                model.add_constraint(
                                    turned_on_var == 1, f"init_turned_on_{self.thermal_unit.name}_{time}"
                                )

    def add_combination_5_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        initial_times: list[DateTime],
        extended_start_date: DateTime,
        power_history: Timeseries | None,
        day_zero: bool,
    ) -> None:
        """Combination 5: T_stop=False, T_start=False, T_stable=True"""

        # Create stable initial condition time frame (excludes the last timestep)
        stable_initial_times = []
        if len(initial_times) > 1:
            stable_initial_times = initial_times[:-1]  # All except the last time step

        if day_zero:
            # DayZero case: All units start OFF
            for time in initial_times:
                # Get state variables
                off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                flat_down_stop_var = model.get_variable(f"flat_down_stop_at_{time}_e_{self.thermal_unit.name}")
                power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                # Fix state variables using equality constraints
                model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")

                # Fix auxiliary variables
                model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(flat_down_stop_var == 0, f"init_flat_down_stop_{self.thermal_unit.name}_{time}")

                # Fix power level to 0
                model.add_constraint(power_level_var == 0, f"init_power_{self.thermal_unit.name}_{time}")

            # Initialize stable-specific variables for dayZero
            for time in stable_initial_times:
                # Get stable state variables
                on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
                on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
                entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
                entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")

                # Fix stable state variables
                model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")

                # Fix stable auxiliary variables
                model.add_constraint(stable_var == 0, f"init_stable_{self.thermal_unit.name}_{time}")
                model.add_constraint(entered_up_var == 0, f"init_entered_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(entered_down_var == 0, f"init_entered_down_{self.thermal_unit.name}_{time}")

            # Initialize gradient auxiliaries to 0 for dayZero
            for time in initial_times:
                u_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.thermal_unit.name}")
                d_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.thermal_unit.name}")
                tilde_u_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.thermal_unit.name}")
                tilde_d_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.thermal_unit.name}")

                model.add_constraint(u_var == 0, f"init_u_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(d_var == 0, f"init_d_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(tilde_u_var == 0, f"init_tilde_u_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(tilde_d_var == 0, f"init_tilde_d_grad_{self.thermal_unit.name}_{time}")

        else:
            # Non-dayZero case: Initialize based on power history
            for time in initial_times:
                if time in power_history.time_index:
                    last_power = power_history.get_value(time)
                    min_power = self.minimum_power.get_value(time)

                    # Get variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                    turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                    turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                    flat_down_stop_var = model.get_variable(f"flat_down_stop_at_{time}_e_{self.thermal_unit.name}")
                    power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                    # Fix power level to historical value
                    model.add_constraint(power_level_var == last_power, f"init_power_{self.thermal_unit.name}_{time}")

                    # Set state variables based on power level relative to minimum power
                    if last_power >= min_power:
                        # Unit is ON and above minimum power
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                    elif last_power > 0:
                        # Unit is ON but below minimum power (in shutdown phase)
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 1, f"init_stop_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is completely OFF
                        model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")

                    # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
                    model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                    model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")
                    model.add_constraint(
                        flat_down_stop_var == 0, f"init_flat_down_stop_{self.thermal_unit.name}_{time}"
                    )

                    # Reconstruct transitions for non-initial times
                    if time != extended_start_date:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)
                            prev_min_power = self.minimum_power.get_value(prev_time)

                            # Detect turn off: entering STOP state
                            if prev_power >= prev_min_power and 0 < last_power < min_power:
                                model.add_constraint(
                                    turned_off_var == 1, f"init_turned_off_{self.thermal_unit.name}_{time}"
                                )

                            # Detect turn on: exiting OFF state
                            elif prev_power == 0 and last_power > 0:
                                model.add_constraint(
                                    turned_on_var == 1, f"init_turned_on_{self.thermal_unit.name}_{time}"
                                )

            # Handle stable-specific variables for non-dayZero
            for i, time in enumerate(stable_initial_times):
                if time in power_history.time_index:
                    current_power = power_history.get_value(time)
                    next_time = time + parameters.timestep
                    next_power = (
                        power_history.get_value(next_time) if next_time in power_history.time_index else current_power
                    )
                    min_power = self.minimum_power.get_value(time)

                    # Get stable state variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                    on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
                    on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                    on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                    stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
                    entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
                    entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")
                    flat_down_stop_var = model.get_variable(f"flat_down_stop_at_{time}_e_{self.thermal_unit.name}")

                    # Initialize auxiliary variables to 0
                    model.add_constraint(stable_var == 0, f"init_stable_{self.thermal_unit.name}_{time}")
                    model.add_constraint(entered_up_var == 0, f"init_entered_up_{self.thermal_unit.name}_{time}")
                    model.add_constraint(entered_down_var == 0, f"init_entered_down_{self.thermal_unit.name}_{time}")

                    # Set stable state variables based on unit state
                    if current_power == 0:
                        # Unit is OFF
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                    elif current_power > 0 and current_power < min_power:
                        # Unit is in STOP state - no UP/DOWN/FLAT allowed
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is ON and above minimum power - determine trend
                        if current_power < next_power:
                            # Power is increasing
                            model.add_constraint(on_up_var == 1, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                        elif current_power > next_power:
                            # Power is decreasing
                            model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 1, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                        else:
                            # Power is stable
                            model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 1, f"init_on_flat_{self.thermal_unit.name}_{time}")

                        # Detect state transitions for non-initial times
                        if time != extended_start_date and current_power > 0:
                            prev_time = time - parameters.timestep
                            if prev_time in power_history.time_index:
                                # Detect entering FLAT state
                                prev_next_time = prev_time + parameters.timestep
                                prev_power = power_history.get_value(prev_time)
                                prev_next_power = (
                                    power_history.get_value(prev_next_time)
                                    if prev_next_time in power_history.time_index
                                    else prev_power
                                )
                                prev_min_power = self.minimum_power.get_value(prev_time)

                                prev_was_flat = prev_power == prev_next_power and prev_power >= prev_min_power
                                current_is_flat = current_power == next_power and current_power >= min_power

                                if not prev_was_flat and current_is_flat:
                                    model.add_constraint(
                                        stable_var == 1, f"init_stable_{self.thermal_unit.name}_{time}"
                                    )

                                # Detect entering UP state
                                prev_was_up = prev_power < prev_next_power and prev_power >= prev_min_power
                                current_is_up = current_power < next_power and current_power >= min_power

                                if not prev_was_up and current_is_up:
                                    model.add_constraint(
                                        entered_up_var == 1, f"init_entered_up_{self.thermal_unit.name}_{time}"
                                    )

                                # Detect entering DOWN state
                                prev_was_down = prev_power > prev_next_power and prev_power >= prev_min_power
                                current_is_down = current_power > next_power and current_power >= min_power

                                if not prev_was_down and current_is_down:
                                    model.add_constraint(
                                        entered_down_var == 1, f"init_entered_down_{self.thermal_unit.name}_{time}"
                                    )

                    # Initialize flat_down_stop (if time index >= 2)
                    if i >= 2:
                        # flat_down_stop = floor((STOP[t] + ON_DOWN[t-1] + ON_FLAT[t-2]) / 3)
                        # For initial conditions, we can compute this from power history
                        time_minus_1 = time - parameters.timestep
                        time_minus_2 = time - 2 * parameters.timestep

                        if time_minus_1 in power_history.time_index and time_minus_2 in power_history.time_index:
                            power_minus_1 = power_history.get_value(time_minus_1)
                            power_minus_2 = power_history.get_value(time_minus_2)
                            min_power_minus_1 = self.minimum_power.get_value(time_minus_1)
                            min_power_minus_2 = self.minimum_power.get_value(time_minus_2)

                            # Get next powers for trend analysis
                            next_time_minus_1 = time_minus_1 + parameters.timestep
                            next_time_minus_2 = time_minus_2 + parameters.timestep

                            next_power_minus_1 = (
                                power_history.get_value(next_time_minus_1)
                                if next_time_minus_1 in power_history.time_index
                                else power_minus_1
                            )
                            next_power_minus_2 = (
                                power_history.get_value(next_time_minus_2)
                                if next_time_minus_2 in power_history.time_index
                                else power_minus_2
                            )

                            # Calculate components
                            stop_component = 1 if (current_power > 0 and current_power < min_power) else 0
                            on_down_component = (
                                1 if (power_minus_1 > next_power_minus_1 and power_minus_1 >= min_power_minus_1) else 0
                            )
                            on_flat_component = (
                                1 if (power_minus_2 == next_power_minus_2 and power_minus_2 >= min_power_minus_2) else 0
                            )

                            flat_down_stop_value = (stop_component + on_down_component + on_flat_component) // 3
                            model.add_constraint(
                                flat_down_stop_var == flat_down_stop_value,
                                f"init_flat_down_stop_{self.thermal_unit.name}_{time}",
                            )
                        else:
                            model.add_constraint(
                                flat_down_stop_var == 0, f"init_flat_down_stop_{self.thermal_unit.name}_{time}"
                            )
                    else:
                        model.add_constraint(
                            flat_down_stop_var == 0, f"init_flat_down_stop_{self.thermal_unit.name}_{time}"
                        )

            # Initialize gradient auxiliaries and flat_down_stop for the last time step
            if len(initial_times) >= 2:
                start_date_minus_one = parameters.start_date - parameters.timestep
                start_date_minus_two = parameters.start_date - 2 * parameters.timestep
                start_date_minus_three = parameters.start_date - 3 * parameters.timestep

                if (
                    start_date_minus_one in power_history.time_index
                    and start_date_minus_two in power_history.time_index
                ):
                    power_minus_one = power_history.get_value(start_date_minus_one)
                    power_minus_two = power_history.get_value(start_date_minus_two)
                    min_power_minus_one = self.minimum_power.get_value(start_date_minus_one)
                    min_power_minus_two = self.minimum_power.get_value(start_date_minus_two)

                    # Get gradient auxiliary variables
                    u_var = model.get_variable(f"UP_grad_at_{start_date_minus_one}_for_e_{self.thermal_unit.name}")
                    d_var = model.get_variable(f"DOWN_grad_at_{start_date_minus_one}_e_{self.thermal_unit.name}")

                    # Calculate gradient values based on power trend
                    power_diff = power_minus_one - power_minus_two

                    # U gradient: only non-zero if unit was in UP state at both time steps
                    if (
                        power_minus_two >= min_power_minus_two
                        and power_minus_one >= min_power_minus_one
                        and power_minus_two < power_minus_one
                    ):
                        model.add_constraint(
                            u_var == power_diff, f"init_u_grad_{self.thermal_unit.name}_{start_date_minus_one}"
                        )
                    else:
                        model.add_constraint(u_var == 0, f"init_u_grad_{self.thermal_unit.name}_{start_date_minus_one}")

                    # D gradient: only non-zero if unit was in DOWN state at both time steps
                    if (
                        power_minus_two >= min_power_minus_two
                        and power_minus_one >= min_power_minus_one
                        and power_minus_two > power_minus_one
                    ):
                        model.add_constraint(
                            d_var == power_diff, f"init_d_grad_{self.thermal_unit.name}_{start_date_minus_one}"
                        )
                    else:
                        model.add_constraint(d_var == 0, f"init_d_grad_{self.thermal_unit.name}_{start_date_minus_one}")

                    # Initialize flat_down_stop for start_date_minus_one
                    if start_date_minus_three in power_history.time_index:
                        power_minus_three = power_history.get_value(start_date_minus_three)
                        min_power_minus_three = self.minimum_power.get_value(start_date_minus_three)

                        # Get next power for trend analysis at time minus 3
                        next_time_minus_three = start_date_minus_three + parameters.timestep
                        next_power_minus_three = (
                            power_history.get_value(next_time_minus_three)
                            if next_time_minus_three in power_history.time_index
                            else power_minus_three
                        )

                        # Calculate flat_down_stop components
                        stop_component = 1 if (power_minus_one > 0 and power_minus_one < min_power_minus_one) else 0
                        on_down_component = (
                            1 if (power_minus_two > power_minus_one and power_minus_two >= min_power_minus_two) else 0
                        )
                        on_flat_component = (
                            1
                            if (
                                power_minus_three == next_power_minus_three
                                and power_minus_three >= min_power_minus_three
                            )
                            else 0
                        )

                        flat_down_stop_value = (stop_component + on_down_component + on_flat_component) // 3
                        flat_down_stop_var = model.get_variable(
                            f"flat_down_stop_at_{start_date_minus_one}_e_{self.thermal_unit.name}"
                        )
                        model.add_constraint(
                            flat_down_stop_var == flat_down_stop_value,
                            f"init_flat_down_stop_{self.thermal_unit.name}_{start_date_minus_one}",
                        )

    def add_combination_6_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        initial_times: list[DateTime],
        extended_start_date: DateTime,
        power_history: Timeseries | None,
        day_zero: bool,
    ) -> None:
        """Combination 6: T_stop=True, T_start=False, T_stable=True"""
        # Create stable initial condition time frame (excludes the last timestep)
        stable_initial_times = []
        if len(initial_times) > 1:
            stable_initial_times = initial_times[:-1]  # All except the last time step

        if day_zero:
            # DayZero case: All units start OFF
            for time in initial_times:
                # Get state variables
                off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                # Fix state variables using equality constraints
                model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")

                # Fix auxiliary variables
                model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")

                # Fix power level to 0
                model.add_constraint(power_level_var == 0, f"init_power_{self.thermal_unit.name}_{time}")

            # Initialize stable-specific variables for dayZero
            for time in stable_initial_times:
                # Get stable state variables
                on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
                on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
                entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
                entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")

                # Fix stable state variables
                model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")

                # Fix stable auxiliary variables
                model.add_constraint(stable_var == 0, f"init_stable_{self.thermal_unit.name}_{time}")
                model.add_constraint(entered_up_var == 0, f"init_entered_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(entered_down_var == 0, f"init_entered_down_{self.thermal_unit.name}_{time}")

            # Initialize gradient auxiliaries to 0 for dayZero
            for time in initial_times:
                u_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.thermal_unit.name}")
                d_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.thermal_unit.name}")
                tilde_u_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.thermal_unit.name}")
                tilde_d_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.thermal_unit.name}")

                model.add_constraint(u_var == 0, f"init_u_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(d_var == 0, f"init_d_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(tilde_u_var == 0, f"init_tilde_u_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(tilde_d_var == 0, f"init_tilde_d_grad_{self.thermal_unit.name}_{time}")

        else:
            # Non-dayZero case: Initialize based on power history
            for time in initial_times:
                if time in power_history.time_index:
                    last_power = power_history.get_value(time)
                    min_power = self.minimum_power.get_value(time)

                    # Get variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                    turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                    turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                    power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                    # Fix power level to historical value
                    model.add_constraint(power_level_var == last_power, f"init_power_{self.thermal_unit.name}_{time}")

                    # Set state variables based on power level relative to minimum power
                    if last_power >= min_power:
                        # Unit is ON and above minimum power
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                    elif last_power > 0:
                        # Unit is ON but below minimum power (in startup phase)
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 1, f"init_start_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is completely OFF
                        model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")

                    # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
                    model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                    model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")

                    # Reconstruct transitions for non-initial times
                    if time != extended_start_date:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)

                            # Detect turn off: unit goes to OFF state
                            if prev_power > 0 and last_power == 0:
                                model.add_constraint(
                                    turned_off_var == 1, f"init_turned_off_{self.thermal_unit.name}_{time}"
                                )

                            # Detect turn on: unit enters START state (from OFF to startup)
                            elif prev_power == 0 and last_power > 0:
                                model.add_constraint(
                                    turned_on_var == 1, f"init_turned_on_{self.thermal_unit.name}_{time}"
                                )

            # Handle stable-specific variables for non-dayZero
            for time in stable_initial_times:
                if time in power_history.time_index:
                    current_power = power_history.get_value(time)
                    next_time = time + parameters.timestep
                    next_power = (
                        power_history.get_value(next_time) if next_time in power_history.time_index else current_power
                    )
                    min_power = self.minimum_power.get_value(time)

                    # Get stable state variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                    on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
                    on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                    on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                    stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
                    entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
                    entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")

                    # Initialize auxiliary variables to 0
                    model.add_constraint(stable_var == 0, f"init_stable_{self.thermal_unit.name}_{time}")
                    model.add_constraint(entered_up_var == 0, f"init_entered_up_{self.thermal_unit.name}_{time}")
                    model.add_constraint(entered_down_var == 0, f"init_entered_down_{self.thermal_unit.name}_{time}")

                    # Set stable state variables based on unit state
                    if current_power == 0:
                        # Unit is OFF
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                    elif current_power > 0 and current_power < min_power:
                        # Unit is in START state - no UP/DOWN/FLAT allowed
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is ON and above minimum power - determine trend
                        if current_power < next_power:
                            # Power is increasing
                            model.add_constraint(on_up_var == 1, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                        elif current_power > next_power:
                            # Power is decreasing
                            model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 1, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                        else:
                            # Power is stable
                            model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 1, f"init_on_flat_{self.thermal_unit.name}_{time}")

                        # Detect state transitions for non-initial times
                        if time != extended_start_date and current_power >= min_power:
                            prev_time = time - parameters.timestep
                            if prev_time in power_history.time_index:
                                # Detect entering FLAT state
                                prev_next_time = prev_time + parameters.timestep
                                prev_power = power_history.get_value(prev_time)
                                prev_next_power = (
                                    power_history.get_value(prev_next_time)
                                    if prev_next_time in power_history.time_index
                                    else prev_power
                                )
                                prev_min_power = self.minimum_power.get_value(prev_time)

                                prev_was_flat = prev_power == prev_next_power and prev_power >= prev_min_power
                                current_is_flat = current_power == next_power and current_power >= min_power

                                if not prev_was_flat and current_is_flat:
                                    model.add_constraint(
                                        stable_var == 1, f"init_stable_{self.thermal_unit.name}_{time}"
                                    )

                                # Detect entering UP state
                                prev_was_up = prev_power < prev_next_power and prev_power >= prev_min_power
                                current_is_up = current_power < next_power and current_power >= min_power

                                if not prev_was_up and current_is_up:
                                    model.add_constraint(
                                        entered_up_var == 1, f"init_entered_up_{self.thermal_unit.name}_{time}"
                                    )

                                # Detect entering DOWN state
                                prev_was_down = prev_power > prev_next_power and prev_power >= prev_min_power
                                current_is_down = current_power > next_power and current_power >= min_power

                                if not prev_was_down and current_is_down:
                                    model.add_constraint(
                                        entered_down_var == 1, f"init_entered_down_{self.thermal_unit.name}_{time}"
                                    )

            # Initialize gradient auxiliaries for the last time step
            if len(initial_times) >= 2:
                start_date_minus_one = parameters.start_date - parameters.timestep
                start_date_minus_two = parameters.start_date - 2 * parameters.timestep

                if (
                    start_date_minus_one in power_history.time_index
                    and start_date_minus_two in power_history.time_index
                ):
                    power_minus_one = power_history.get_value(start_date_minus_one)
                    power_minus_two = power_history.get_value(start_date_minus_two)
                    min_power_minus_one = self.minimum_power.get_value(start_date_minus_one)
                    min_power_minus_two = self.minimum_power.get_value(start_date_minus_two)

                    # Get gradient auxiliary variables
                    u_var = model.get_variable(f"UP_grad_at_{start_date_minus_one}_for_e_{self.thermal_unit.name}")
                    d_var = model.get_variable(f"DOWN_grad_at_{start_date_minus_one}_e_{self.thermal_unit.name}")

                    # Calculate gradient values based on power trend
                    power_diff = power_minus_one - power_minus_two

                    # U gradient: only non-zero if unit was in UP state at both time steps
                    if (
                        power_minus_two >= min_power_minus_two
                        and power_minus_one >= min_power_minus_one
                        and power_minus_two < power_minus_one
                    ):
                        model.add_constraint(
                            u_var == power_diff, f"init_u_grad_{self.thermal_unit.name}_{start_date_minus_one}"
                        )
                    else:
                        model.add_constraint(u_var == 0, f"init_u_grad_{self.thermal_unit.name}_{start_date_minus_one}")

                    # D gradient: only non-zero if unit was in DOWN state at both time steps
                    if (
                        power_minus_two >= min_power_minus_two
                        and power_minus_one >= min_power_minus_one
                        and power_minus_two > power_minus_one
                    ):
                        model.add_constraint(
                            d_var == power_diff, f"init_d_grad_{self.thermal_unit.name}_{start_date_minus_one}"
                        )
                    else:
                        model.add_constraint(d_var == 0, f"init_d_grad_{self.thermal_unit.name}_{start_date_minus_one}")

    def add_combination_7_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        initial_times: list[DateTime],
        extended_start_date: DateTime,
        power_history: Timeseries | None,
        day_zero: bool,
    ) -> None:
        """Combination 7: T_stop=False, T_start=True, T_stable=True"""
        if day_zero:
            # DayZero case: All units start OFF
            for time in initial_times:
                # Get state variables
                off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                down_to_stop_var = model.get_variable(f"down_to_stop_grad_at_{time}_e_{self.thermal_unit.name}")
                power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                # Fix state variables using equality constraints
                model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")

                # Fix auxiliary variables
                model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(down_to_stop_var == 0, f"init_down_to_stop_{self.thermal_unit.name}_{time}")

                # Fix power level to 0
                model.add_constraint(power_level_var == 0, f"init_power_{self.thermal_unit.name}_{time}")
        else:
            # Non-dayZero case: Initialize based on power history
            for time in initial_times:
                if time in power_history.time_index:
                    last_power = power_history.get_value(time)
                    min_power = self.minimum_power.get_value(time)

                    # Get variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                    start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                    on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                    on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                    turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                    turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                    down_to_stop_var = model.get_variable(f"down_to_stop_grad_at_{time}_e_{self.thermal_unit.name}")
                    power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                    # Fix power level to historical value
                    model.add_constraint(power_level_var == last_power, f"init_power_{self.thermal_unit.name}_{time}")

                    # Set state variables based on power level relative to minimum power
                    if last_power >= min_power:
                        # Unit is ON and above minimum power (normal operation)
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                        # Set both ON states to 1 to allow flexibility (no stable constraints)
                        model.add_constraint(on_down_var == 1, f"init_on_down_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 1, f"init_on_up_{self.thermal_unit.name}_{time}")
                    elif last_power > 0:
                        # Unit is ON but below minimum power (startup or shutdown phase)
                        # Initially set both START and STOP to 1, distinguish later based on trend
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 1, f"init_stop_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 1, f"init_start_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is completely OFF
                        model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")

                    # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
                    model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                    model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")
                    model.add_constraint(down_to_stop_var == 0, f"init_down_to_stop_{self.thermal_unit.name}_{time}")

                    # Distinguish between startup and shutdown for intermediate power levels
                    if time != extended_start_date and 0 < last_power < min_power:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)

                            # If power is increasing, we are starting up
                            if last_power > prev_power:
                                model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                                model.add_constraint(start_var == 1, f"init_start_{self.thermal_unit.name}_{time}")
                            # If power is decreasing, we are shutting down
                            elif last_power < prev_power:
                                model.add_constraint(stop_var == 1, f"init_stop_{self.thermal_unit.name}_{time}")
                                model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                            # If power is stable, keep both (handled by constraints)

                    # Reconstruct transitions for non-initial times
                    if time != extended_start_date:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)
                            prev_min_power = self.minimum_power.get_value(prev_time)

                            # Detect turn off: entering STOP state
                            if prev_power >= prev_min_power and 0 < last_power < min_power and last_power < prev_power:
                                model.add_constraint(
                                    turned_off_var == 1, f"init_turned_off_{self.thermal_unit.name}_{time}"
                                )

                            # Detect turn on: entering START state
                            elif prev_power == 0 and last_power > 0:
                                model.add_constraint(
                                    turned_on_var == 1, f"init_turned_on_{self.thermal_unit.name}_{time}"
                                )

                            # Detect down_to_stop transition
                            # This occurs when unit goes from ON_DOWN to STOP
                            if (
                                0 < last_power < min_power  # Currently in STOP
                                and prev_power >= prev_min_power
                                and last_power < prev_power
                            ):  # Previously operational and decreasing
                                model.add_constraint(
                                    down_to_stop_var == 1, f"init_down_to_stop_{self.thermal_unit.name}_{time}"
                                )

    def add_combination_8_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        initial_times: list[DateTime],
        extended_start_date: DateTime,
        power_history: Timeseries | None,
        day_zero: bool,
    ) -> None:
        """Combination 8: T_stop=True, T_start=True, T_stable=True"""
        # Create stable initial condition time frame (excludes the last timestep)
        stable_initial_times = []
        if len(initial_times) > 1:
            stable_initial_times = initial_times[:-1]  # All except the last time step

        if day_zero:
            # DayZero case: All units start OFF
            for time in initial_times:
                # Get state variables
                off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                # Fix state variables using equality constraints
                model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")

                # Fix auxiliary variables
                model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")

                # Fix power level to 0
                model.add_constraint(power_level_var == 0, f"init_power_{self.thermal_unit.name}_{time}")

            # Initialize stable-specific variables for dayZero
            for time in stable_initial_times:
                # Get stable state variables
                on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
                on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
                entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
                entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")
                flat_down_stop_var = model.get_variable(f"flat_down_stop_at_{time}_e_{self.thermal_unit.name}")

                # Fix stable state variables
                model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")

                # Fix stable auxiliary variables
                model.add_constraint(stable_var == 0, f"init_stable_{self.thermal_unit.name}_{time}")
                model.add_constraint(entered_up_var == 0, f"init_entered_up_{self.thermal_unit.name}_{time}")
                model.add_constraint(entered_down_var == 0, f"init_entered_down_{self.thermal_unit.name}_{time}")
                model.add_constraint(flat_down_stop_var == 0, f"init_flat_down_stop_{self.thermal_unit.name}_{time}")

            # Initialize gradient auxiliaries to 0 for dayZero
            for time in initial_times:
                u_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.thermal_unit.name}")
                d_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.thermal_unit.name}")
                tilde_u_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.thermal_unit.name}")
                tilde_d_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.thermal_unit.name}")

                model.add_constraint(u_var == 0, f"init_u_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(d_var == 0, f"init_d_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(tilde_u_var == 0, f"init_tilde_u_grad_{self.thermal_unit.name}_{time}")
                model.add_constraint(tilde_d_var == 0, f"init_tilde_d_grad_{self.thermal_unit.name}_{time}")

        else:
            # Non-dayZero case: Initialize based on power history
            for time in initial_times:
                if time in power_history.time_index:
                    last_power = power_history.get_value(time)
                    min_power = self.minimum_power.get_value(time)

                    # Get variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                    start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                    turned_on_var = model.get_variable(f"t_on_of_e_{self.thermal_unit.name}_at_{time}")
                    turned_off_var = model.get_variable(f"t_off_of_e_{self.thermal_unit.name}_at_{time}")
                    power_level_var = model.get_variable(f"{self.thermal_unit.name}_p_lev_{time}")

                    # Fix power level to historical value
                    model.add_constraint(power_level_var == last_power, f"init_power_{self.thermal_unit.name}_{time}")

                    # Set state variables based on power level relative to minimum power
                    if last_power >= min_power:
                        # Unit is ON and above minimum power (normal operation)
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                    elif last_power > 0:
                        # Unit is ON but below minimum power (startup or shutdown phase)
                        # Initially set both START and STOP to 1, distinguish later based on trend
                        model.add_constraint(off_var == 0, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 1, f"init_start_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 1, f"init_stop_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is completely OFF
                        model.add_constraint(off_var == 1, f"init_off_{self.thermal_unit.name}_{time}")
                        model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                        model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")

                    # Initialize auxiliary variables to 0 (will be reconstructed from transitions)
                    model.add_constraint(turned_on_var == 0, f"init_turned_on_{self.thermal_unit.name}_{time}")
                    model.add_constraint(turned_off_var == 0, f"init_turned_off_{self.thermal_unit.name}_{time}")

                    # Distinguish between startup and shutdown for intermediate power levels
                    if time != extended_start_date and 0 < last_power < min_power:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)

                            # If power is increasing, we are starting up
                            if last_power > prev_power:
                                model.add_constraint(stop_var == 0, f"init_stop_{self.thermal_unit.name}_{time}")
                                model.add_constraint(start_var == 1, f"init_start_{self.thermal_unit.name}_{time}")
                            # If power is decreasing, we are shutting down
                            elif last_power < prev_power:
                                model.add_constraint(stop_var == 1, f"init_stop_{self.thermal_unit.name}_{time}")
                                model.add_constraint(start_var == 0, f"init_start_{self.thermal_unit.name}_{time}")
                            # If power is stable, keep both (handled by constraints)

                    # Reconstruct transitions for non-initial times
                    if time != extended_start_date:
                        prev_time = time - parameters.timestep
                        if prev_time in power_history.time_index:
                            prev_power = power_history.get_value(prev_time)

                            # Detect turn off: entering STOP state
                            if prev_power > 0 and last_power == 0:
                                model.add_constraint(
                                    turned_off_var == 1, f"init_turned_off_{self.thermal_unit.name}_{time}"
                                )

                            # Detect turn on: entering START state
                            elif prev_power == 0 and last_power > 0:
                                model.add_constraint(
                                    turned_on_var == 1, f"init_turned_on_{self.thermal_unit.name}_{time}"
                                )

            # Handle stable-specific variables for non-dayZero
            for i, time in enumerate(stable_initial_times):
                if time in power_history.time_index:
                    current_power = power_history.get_value(time)
                    next_time = time + parameters.timestep
                    next_power = (
                        power_history.get_value(next_time) if next_time in power_history.time_index else current_power
                    )
                    min_power = self.minimum_power.get_value(time)

                    # Get stable state variables
                    off_var = model.get_variable(f"OFF_var_e_{self.thermal_unit.name}_at_{time}")
                    start_var = model.get_variable(f"ON_START_e_{self.thermal_unit.name}_at_{time}")
                    stop_var = model.get_variable(f"STOP_e_{self.thermal_unit.name}_at_{time}")
                    on_flat_var = model.get_variable(f"ON_FLAT_e_{self.thermal_unit.name}_at_{time}")
                    on_up_var = model.get_variable(f"ON_UP_var_e_{self.thermal_unit.name}_at_{time}")
                    on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.thermal_unit.name}_at_{time}")
                    stable_var = model.get_variable(f"stable_at_{time}_e_{self.thermal_unit.name}")
                    entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.thermal_unit.name}")
                    entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.thermal_unit.name}")
                    flat_down_stop_var = model.get_variable(f"flat_down_stop_at_{time}_e_{self.thermal_unit.name}")

                    # Initialize auxiliary variables to 0
                    model.add_constraint(stable_var == 0, f"init_stable_{self.thermal_unit.name}_{time}")
                    model.add_constraint(entered_up_var == 0, f"init_entered_up_{self.thermal_unit.name}_{time}")
                    model.add_constraint(entered_down_var == 0, f"init_entered_down_{self.thermal_unit.name}_{time}")

                    # Set stable state variables based on unit state
                    if current_power == 0:
                        # Unit is OFF
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                    elif current_power > 0 and current_power < min_power:
                        # Unit is in START or STOP state - no UP/DOWN/FLAT allowed
                        model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                        model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                    else:
                        # Unit is ON and above minimum power - determine trend
                        if current_power < next_power:
                            # Power is increasing
                            model.add_constraint(on_up_var == 1, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                        elif current_power > next_power:
                            # Power is decreasing
                            model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 1, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 0, f"init_on_flat_{self.thermal_unit.name}_{time}")
                        else:
                            # Power is stable
                            model.add_constraint(on_up_var == 0, f"init_on_up_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_down_var == 0, f"init_on_down_{self.thermal_unit.name}_{time}")
                            model.add_constraint(on_flat_var == 1, f"init_on_flat_{self.thermal_unit.name}_{time}")

                        # Detect state transitions for non-initial times
                        if time != extended_start_date and current_power >= min_power:
                            prev_time = time - parameters.timestep
                            if prev_time in power_history.time_index:
                                # Detect entering FLAT state
                                prev_next_time = prev_time + parameters.timestep
                                prev_power = power_history.get_value(prev_time)
                                prev_next_power = (
                                    power_history.get_value(prev_next_time)
                                    if prev_next_time in power_history.time_index
                                    else prev_power
                                )
                                prev_min_power = self.minimum_power.get_value(prev_time)

                                prev_was_flat = prev_power == prev_next_power and prev_power >= prev_min_power
                                current_is_flat = current_power == next_power and current_power >= min_power

                                if not prev_was_flat and current_is_flat:
                                    model.add_constraint(
                                        stable_var == 1, f"init_stable_{self.thermal_unit.name}_{time}"
                                    )

                                # Detect entering UP state
                                prev_was_up = prev_power < prev_next_power and prev_power >= prev_min_power
                                current_is_up = current_power < next_power and current_power >= min_power

                                if not prev_was_up and current_is_up:
                                    model.add_constraint(
                                        entered_up_var == 1, f"init_entered_up_{self.thermal_unit.name}_{time}"
                                    )

                                # Detect entering DOWN state
                                prev_was_down = prev_power > prev_next_power and prev_power >= prev_min_power
                                current_is_down = current_power > next_power and current_power >= min_power

                                if not prev_was_down and current_is_down:
                                    model.add_constraint(
                                        entered_down_var == 1, f"init_entered_down_{self.thermal_unit.name}_{time}"
                                    )

                    # Initialize flat_down_stop (if time index >= 2)
                    if i >= 2:
                        # flat_down_stop = floor((STOP[t] + ON_DOWN[t-1] + ON_FLAT[t-2]) / 3)
                        time_minus_1 = time - parameters.timestep
                        time_minus_2 = time - 2 * parameters.timestep

                        if time_minus_1 in power_history.time_index and time_minus_2 in power_history.time_index:
                            power_minus_1 = power_history.get_value(time_minus_1)
                            power_minus_2 = power_history.get_value(time_minus_2)
                            min_power_minus_1 = self.minimum_power.get_value(time_minus_1)
                            min_power_minus_2 = self.minimum_power.get_value(time_minus_2)

                            # Get next powers for trend analysis
                            next_time_minus_1 = time_minus_1 + parameters.timestep
                            next_time_minus_2 = time_minus_2 + parameters.timestep

                            next_power_minus_1 = (
                                power_history.get_value(next_time_minus_1)
                                if next_time_minus_1 in power_history.time_index
                                else power_minus_1
                            )
                            next_power_minus_2 = (
                                power_history.get_value(next_time_minus_2)
                                if next_time_minus_2 in power_history.time_index
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
                                f"init_flat_down_stop_{self.thermal_unit.name}_{time}",
                            )
                        else:
                            model.add_constraint(
                                flat_down_stop_var == 0, f"init_flat_down_stop_{self.thermal_unit.name}_{time}"
                            )
                    else:
                        model.add_constraint(
                            flat_down_stop_var == 0, f"init_flat_down_stop_{self.thermal_unit.name}_{time}"
                        )

            # Initialize gradient auxiliaries and flat_down_stop for the last time step
            if len(initial_times) >= 2:
                start_date_minus_one = parameters.start_date - parameters.timestep
                start_date_minus_two = parameters.start_date - 2 * parameters.timestep
                start_date_minus_three = parameters.start_date - 3 * parameters.timestep

                if (
                    start_date_minus_one in power_history.time_index
                    and start_date_minus_two in power_history.time_index
                ):
                    power_minus_one = power_history.get_value(start_date_minus_one)
                    power_minus_two = power_history.get_value(start_date_minus_two)
                    min_power_minus_one = self.minimum_power.get_value(start_date_minus_one)
                    min_power_minus_two = self.minimum_power.get_value(start_date_minus_two)

                    # Get gradient auxiliary variables
                    u_var = model.get_variable(f"UP_grad_at_{start_date_minus_one}_for_e_{self.thermal_unit.name}")
                    d_var = model.get_variable(f"DOWN_grad_at_{start_date_minus_one}_e_{self.thermal_unit.name}")

                    # Calculate gradient values based on power trend
                    power_diff = power_minus_one - power_minus_two

                    # U gradient: only non-zero if unit was in UP state at both time steps
                    if (
                        power_minus_two >= min_power_minus_two
                        and power_minus_one >= min_power_minus_one
                        and power_minus_two < power_minus_one
                    ):
                        model.add_constraint(
                            u_var == power_diff, f"init_u_grad_{self.thermal_unit.name}_{start_date_minus_one}"
                        )
                    else:
                        model.add_constraint(u_var == 0, f"init_u_grad_{self.thermal_unit.name}_{start_date_minus_one}")

                    # D gradient: only non-zero if unit was in DOWN state at both time steps
                    if (
                        power_minus_two >= min_power_minus_two
                        and power_minus_one >= min_power_minus_one
                        and power_minus_two > power_minus_one
                    ):
                        model.add_constraint(
                            d_var == power_diff, f"init_d_grad_{self.thermal_unit.name}_{start_date_minus_one}"
                        )
                    else:
                        model.add_constraint(d_var == 0, f"init_d_grad_{self.thermal_unit.name}_{start_date_minus_one}")

                    # Initialize flat_down_stop for start_date_minus_one
                    if start_date_minus_three in power_history.time_index:
                        power_minus_three = power_history.get_value(start_date_minus_three)
                        min_power_minus_three = self.minimum_power.get_value(start_date_minus_three)

                        # Get next power for trend analysis at time minus 3
                        next_time_minus_three = start_date_minus_three + parameters.timestep
                        next_power_minus_three = (
                            power_history.get_value(next_time_minus_three)
                            if next_time_minus_three in power_history.time_index
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
                            if (
                                power_minus_three == next_power_minus_three
                                and power_minus_three >= min_power_minus_three
                            )
                            else 0
                        )

                        flat_down_stop_value = (stop_component + on_down_component + on_flat_component) // 3
                        flat_down_stop_var = model.get_variable(
                            f"flat_down_stop_at_{start_date_minus_one}_e_{self.thermal_unit.name}"
                        )
                        model.add_constraint(
                            flat_down_stop_var == flat_down_stop_value,
                            f"init_flat_down_stop_{self.thermal_unit.name}_{start_date_minus_one}",
                        )
