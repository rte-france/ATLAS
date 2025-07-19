"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import math
from typing import Any

from pendulum import DateTime
from pydantic import model_validator

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated, get_variable_cost
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel


class ThermalPO(Thermal):
    """
    Sophisticated unit commitment model for thermal power equipment.

    This implements a state-of-the-art thermal unit optimization with multiple
    operational states, complex time constraints, and ramping limitations.
    """

    maximum_fcr: float
    maximum_afrr: float
    minimum_power: Timeseries | LazyTimeseries
    maximum_power: Timeseries | LazyTimeseries
    variable_cost: Timeseries | LazyTimeseries
    startup_cost: Timeseries | LazyTimeseries
    maximum_gradient: float = 0.0  # MW/min ramping rate
    has_daily_energy_constraint: bool = False

    # Reserve procurement forecasts
    afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    afrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    mfrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    mfrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    rr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    rr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    fcr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    fcr_down_procured: ForecastingMatrix | LazyForecastingMatrix

    # Internal time step parameters (computed from time durations)
    _T_on: int = 0
    _T_off: int = 0
    _T_start: int = 0
    _T_stop: int = 0
    _T_stable: int = 0
    _Delta_Q: float = 0.0
    _Delta_Q_unconstrained: float = 0.0
    _combination: int = 1  # Which constraint combination to use (1-8)

    def _compute_time_parameters(self, parameters: PortfolioOptimisationParameters):
        """Compute time step parameters from duration constraints."""
        timestep_minutes = parameters.timestep.total_minutes()

        # Convert time durations to time steps
        if self.minimum_time_on and self.minimum_time_on.total_minutes() > 0:
            self._T_on = int(max(1, math.ceil(self.minimum_time_on.total_minutes() / timestep_minutes))) + 1
        else:
            self._T_on = 0

        if self.minimum_time_off and self.minimum_time_off.total_minutes() > 0:
            self._T_off = int(max(1, math.ceil(self.minimum_time_off.total_minutes() / timestep_minutes))) + 1
        else:
            self._T_off = 0

        if self.startup_duration:
            self._T_start = int(math.floor(self.startup_duration.total_minutes() / timestep_minutes))
        else:
            self._T_start = 0

        if self.shutdown_duration:
            self._T_stop = int(math.floor(self.shutdown_duration.total_minutes() / timestep_minutes))
        else:
            self._T_stop = 0

        if self.minimum_stable_power_duration:
            if self.minimum_stable_power_duration.total_minutes() < timestep_minutes:
                self._T_stable = 0
            else:
                self._T_stable = (
                    int(math.ceil(self.minimum_stable_power_duration.total_minutes() / timestep_minutes)) + 1
                )
                # Rescale T_stable so that it is either equal to 0 or >= 2
                self._T_stable = self._T_stable if self._T_stable >= 2 else 0
        else:
            self._T_stable = 0

        # Ramping parameters
        self._Delta_Q = self.maximum_gradient * timestep_minutes
        self._Delta_Q_unconstrained = max(self.maximum_power.max(), 1000.0)  # Large value for unconstrained ramping

        # Determine which constraint combination to use
        self._combination = self._determine_combination()

    def _determine_combination(self) -> int:
        """Determine which of the 8 constraint combinations to use."""
        if self._T_stop == 0 and self._T_start == 0 and self._T_stable == 0:
            return 1
        elif self._T_stop >= 1 and self._T_start == 0 and self._T_stable == 0:
            return 2
        elif self._T_stop == 0 and self._T_start == 0 and self._T_stable >= 1:
            return 3
        elif self._T_start >= 1 and self._T_stop == 0 and self._T_stable == 0:
            return 4
        elif self._T_stop >= 1 and self._T_start == 0 and self._T_stable >= 1:
            return 5
        elif self._T_stop == 0 and self._T_start >= 1 and self._T_stable >= 1:
            return 6
        elif self._T_stop >= 1 and self._T_start >= 1 and self._T_stable == 0:
            return 7
        elif self._T_stop >= 1 and self._T_start >= 1 and self._T_stable >= 1:
            return 8
        else:
            return 1  # Default fallback

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """Build variables for complex thermal unit commitment."""
        self._compute_time_parameters(parameters)

        for time in parameters.thermal_op_times:
            min_power = self.minimum_power.get_value(time)
            max_power = self.maximum_power.get_value(time)
            maximum_automated = get_maximum_automated(self)

            # Core power and auxiliary variables
            model.add_continuous_variable(
                name=f"{self.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

            model.add_continuous_variable(
                name=f"{self.name}_additional_power_above_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

            model.add_continuous_variable(
                name=f"{self.name}_additional_power_below_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

            # Core state variables (always present)
            model.add_boolean_variable(name=f"{self.name}_OFF_{time}")
            model.add_boolean_variable(name=f"{self.name}_ON_UP_{time}")
            model.add_boolean_variable(name=f"{self.name}_ON_DOWN_{time}")

            # Core auxiliary variables
            model.add_boolean_variable(name=f"{self.name}_turned_on_{time}")
            model.add_boolean_variable(name=f"{self.name}_turned_off_{time}")

            # Conditional state variables based on combination
            if self._T_start >= 1:
                model.add_boolean_variable(name=f"{self.name}_START_{time}")

            if self._T_stop >= 1:
                model.add_boolean_variable(name=f"{self.name}_STOP_{time}")

            if self._T_stable >= 1:
                model.add_boolean_variable(name=f"{self.name}_ON_FLAT_{time}")
                model.add_boolean_variable(name=f"{self.name}_stable_{time}")
                model.add_boolean_variable(name=f"{self.name}_entered_up_{time}")
                model.add_boolean_variable(name=f"{self.name}_entered_down_{time}")

            # Additional auxiliary variables for complex combinations
            if self._T_stop >= 1 and self._T_start == 0 and self._T_stable == 0:
                model.add_boolean_variable(name=f"{self.name}_down_to_stop_{time}")

            if self._T_stop >= 1 and self._T_stable >= 1:
                model.add_boolean_variable(name=f"{self.name}_flat_down_stop_{time}")

            if self._T_stop >= 1 and self._T_start >= 1 and self._T_stable == 0:
                model.add_boolean_variable(name=f"{self.name}_down_to_stop_{time}")

            add_reserve_variables(
                model,
                self.name,
                time,
                min_power,
                max_power,
                maximum_automated,
                thermal_equipment=True,
                relaxed_reserves=True,
            )

            # Gradient auxiliary variables for complex ramping
            if self._T_stable >= 1:
                Q_max = max_power
                Q_min = -Q_max

                # 2-stage gradient variables (U, tilde_U, D, tilde_D)
                model.add_continuous_variable(
                    name=f"{self.name}_U_{time}",
                    lower_bound=Q_min,
                    upper_bound=Q_max,
                )
                model.add_continuous_variable(
                    name=f"{self.name}_tilde_U_{time}",
                    lower_bound=Q_min,
                    upper_bound=Q_max,
                )
                model.add_continuous_variable(
                    name=f"{self.name}_D_{time}",
                    lower_bound=Q_min,
                    upper_bound=Q_max,
                )
                model.add_continuous_variable(
                    name=f"{self.name}_tilde_D_{time}",
                    lower_bound=Q_min,
                    upper_bound=Q_max,
                )

                # DD variable for complex combinations
                if self._T_start >= 1 or self._T_stop >= 1:
                    model.add_continuous_variable(
                        name=f"{self.name}_DD_{time}",
                        lower_bound=Q_min,
                        upper_bound=Q_max,
                    )

    def add_constraints(
        self,
        time: DateTime,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """Add constraints based on the determined combination."""
        if time not in parameters.thermal_op_times:
            return

        # Delegate to the appropriate combination method
        combination_methods = {
            1: self._add_combination_1_constraints,
            2: self._add_combination_2_constraints,
            3: self._add_combination_3_constraints,
            4: self._add_combination_4_constraints,
            5: self._add_combination_5_constraints,
            6: self._add_combination_6_constraints,
            7: self._add_combination_7_constraints,
            8: self._add_combination_8_constraints,
        }

        method = combination_methods.get(self._combination, self._add_combination_1_constraints)
        method(time, model, parameters)

    def _add_combination_1_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 1: T_stop = T_stable = T_start = 0 (Basic 3-state model)."""
        min_power = self.minimum_power.get_value(time)
        max_power = self.maximum_power.get_value(time)

        # Get variables
        power_level = model.get_variable(f"{self.name}_power_level_{time}")
        OFF = model.get_variable(f"{self.name}_OFF_{time}")
        ON_UP = model.get_variable(f"{self.name}_ON_UP_{time}")
        ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{time}")
        turned_on = model.get_variable(f"{self.name}_turned_on_{time}")
        turned_off = model.get_variable(f"{self.name}_turned_off_{time}")

        # Mutual exclusion constraint
        model.add_constraint(OFF + ON_UP + ON_DOWN == 1)

        # Power constraints
        model.add_constraint(power_level >= min_power * (ON_UP + ON_DOWN))
        model.add_constraint(power_level <= max_power * (ON_UP + ON_DOWN))

        # Auxiliary variable definition constraints
        time_idx = parameters.thermal_op_times.index(time)
        if time_idx > 0:
            prev_time = parameters.thermal_op_times[time_idx - 1]
            prev_OFF = model.get_variable(f"{self.name}_OFF_{prev_time}")

            # turned_on constraints
            model.add_constraint(turned_on <= 1 - OFF)
            model.add_constraint(turned_on <= prev_OFF)
            model.add_constraint(turned_on >= prev_OFF - OFF)

            # turned_off constraints
            model.add_constraint(turned_off <= OFF)
            model.add_constraint(turned_off <= 1 - prev_OFF)
            model.add_constraint(turned_off >= OFF - prev_OFF)

        # Reserve constraints
        self._add_reserve_constraints(time, model, parameters)

        # Minimum time constraints
        self._add_minimum_time_constraints(time, model, parameters, "combination_1")

        # Ramping constraints
        self._add_ramping_constraints(time, model, parameters, "combination_1")

        # Daily energy constraints
        self._add_daily_energy_constraints(time, model, parameters)

    def _add_combination_2_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 2: T_stop >= 1, T_start = 0, T_stable = 0."""
        min_power = self.minimum_power.get_value(time)
        max_power = self.maximum_power.get_value(time)

        # Get variables
        power_level = model.get_variable(f"{self.name}_power_level_{time}")
        OFF = model.get_variable(f"{self.name}_OFF_{time}")
        ON_UP = model.get_variable(f"{self.name}_ON_UP_{time}")
        ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{time}")
        STOP = model.get_variable(f"{self.name}_STOP_{time}")
        turned_off = model.get_variable(f"{self.name}_turned_off_{time}")
        down_to_stop = model.get_variable(f"{self.name}_down_to_stop_{time}")

        # Mutual exclusion constraint
        model.add_constraint(OFF + ON_UP + ON_DOWN + STOP == 1)

        # Power constraints
        model.add_constraint(power_level >= min_power * (ON_UP + ON_DOWN))
        model.add_constraint(power_level <= max_power * (ON_UP + ON_DOWN + STOP))

        # Auxiliary variable constraints
        time_idx = parameters.thermal_op_times.index(time)
        if time_idx > 0:
            prev_time = parameters.thermal_op_times[time_idx - 1]
            prev_STOP = model.get_variable(f"{self.name}_STOP_{prev_time}")
            prev_ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{prev_time}")

            # Complex auxiliary variable definitions for STOP transitions
            model.add_constraint(turned_off <= STOP)
            model.add_constraint(turned_off <= 1 - prev_STOP)
            model.add_constraint(turned_off >= STOP - prev_STOP)

            # down_to_stop transition
            model.add_constraint(down_to_stop <= STOP)
            model.add_constraint(down_to_stop <= prev_ON_DOWN)
            model.add_constraint(down_to_stop >= STOP + prev_ON_DOWN - 1)

        # Eviction constraints for shutdown duration
        self._add_eviction_constraints(time, model, parameters, "STOP", self._T_stop)

        # Reserve constraints
        self._add_reserve_constraints(time, model, parameters)

        # Minimum time constraints
        self._add_minimum_time_constraints(time, model, parameters, "combination_2")

        # Ramping constraints
        self._add_ramping_constraints(time, model, parameters, "combination_2")

        # Shutdown gradient constraints
        self._add_shutdown_gradient_constraints(time, model, parameters)

        # Daily energy constraints
        self._add_daily_energy_constraints(time, model, parameters)

    def _add_combination_3_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 3: T_stop = 0, T_start = 0, T_stable >= 1."""
        min_power = self.minimum_power.get_value(time)
        max_power = self.maximum_power.get_value(time)

        # Get variables
        power_level = model.get_variable(f"{self.name}_power_level_{time}")
        OFF = model.get_variable(f"{self.name}_OFF_{time}")
        ON_UP = model.get_variable(f"{self.name}_ON_UP_{time}")
        ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{time}")
        ON_FLAT = model.get_variable(f"{self.name}_ON_FLAT_{time}")
        stable = model.get_variable(f"{self.name}_stable_{time}")
        entered_up = model.get_variable(f"{self.name}_entered_up_{time}")
        entered_down = model.get_variable(f"{self.name}_entered_down_{time}")

        # Mutual exclusion constraint
        model.add_constraint(OFF + ON_UP + ON_DOWN + ON_FLAT == 1)

        # Power constraints
        model.add_constraint(power_level >= min_power * (ON_UP + ON_DOWN + ON_FLAT))
        model.add_constraint(power_level <= max_power * (ON_UP + ON_DOWN + ON_FLAT))

        # Complex auxiliary variable definitions for stable operations
        time_idx = parameters.thermal_op_times.index(time)
        if time_idx > 0:
            prev_time = parameters.thermal_op_times[time_idx - 1]
            prev_ON_FLAT = model.get_variable(f"{self.name}_ON_FLAT_{prev_time}")
            prev_ON_UP = model.get_variable(f"{self.name}_ON_UP_{prev_time}")
            prev_ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{prev_time}")

            # stable transition constraints
            model.add_constraint(stable <= ON_FLAT)
            model.add_constraint(stable <= 1 - prev_ON_FLAT)
            model.add_constraint(stable >= ON_FLAT - prev_ON_FLAT)

            # entered_up constraints
            model.add_constraint(entered_up <= ON_UP)
            model.add_constraint(entered_up <= 1 - prev_ON_UP)
            model.add_constraint(entered_up >= ON_UP - prev_ON_UP)

            # entered_down constraints
            model.add_constraint(entered_down <= ON_DOWN)
            model.add_constraint(entered_down <= 1 - prev_ON_DOWN)
            model.add_constraint(entered_down >= ON_DOWN - prev_ON_DOWN)

        # Reserve constraints
        self._add_reserve_constraints(time, model, parameters)

        # Complete 2-stage gradient constraints for stable operation
        self._add_complete_gradient_constraints(time, model, parameters)

        # Minimum stable duration constraints
        self._add_minimum_stable_constraints(time, model, parameters)

        # Daily energy constraints
        self._add_daily_energy_constraints(time, model, parameters)

    def _add_combination_4_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 4: T_start >= 1, T_stop = 0, T_stable = 0."""
        # Similar structure to combination 2 but with START instead of STOP
        min_power = self.minimum_power.get_value(time)
        max_power = self.maximum_power.get_value(time)

        # Get variables
        power_level = model.get_variable(f"{self.name}_power_level_{time}")
        OFF = model.get_variable(f"{self.name}_OFF_{time}")
        ON_UP = model.get_variable(f"{self.name}_ON_UP_{time}")
        ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{time}")
        START = model.get_variable(f"{self.name}_START_{time}")

        # Mutual exclusion constraint
        model.add_constraint(OFF + ON_UP + ON_DOWN + START == 1)

        # Power constraints with startup considerations
        model.add_constraint(power_level >= min_power * (ON_UP + ON_DOWN))
        model.add_constraint(power_level <= max_power * (ON_UP + ON_DOWN + START))

        # Eviction constraints for startup duration
        self._add_eviction_constraints(time, model, parameters, "START", self._T_start)

        # Reserve constraints
        self._add_reserve_constraints(time, model, parameters)

        # Complete gradient constraints
        self._add_complete_gradient_constraints(time, model, parameters)

        # Daily energy constraints
        self._add_daily_energy_constraints(time, model, parameters)

    def _add_combination_5_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 5: T_stop >= 1, T_start = 0, T_stable >= 1."""
        # Combines STOP and ON_FLAT states
        self._add_combination_2_constraints(time, model, parameters)
        self._add_combination_3_constraints(time, model, parameters)

        # Additional constraints for STOP + FLAT interactions
        flat_down_stop = model.get_variable(f"{self.name}_flat_down_stop_{time}")
        STOP = model.get_variable(f"{self.name}_STOP_{time}")

        # Complex flat_down_stop calculation
        time_idx = parameters.thermal_op_times.index(time)
        if time_idx >= 2:
            prev_time = parameters.thermal_op_times[time_idx - 1]
            prev2_time = parameters.thermal_op_times[time_idx - 2]
            prev_ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{prev_time}")
            prev2_ON_FLAT = model.get_variable(f"{self.name}_ON_FLAT_{prev2_time}")

            # flat_down_stop = floor((STOP + ON_DOWN[t-1] + ON_FLAT[t-2]) / 3)
            model.add_constraint(3 * flat_down_stop <= STOP + prev_ON_DOWN + prev2_ON_FLAT)
            model.add_constraint(3 * flat_down_stop >= STOP + prev_ON_DOWN + prev2_ON_FLAT - 2)

        # Specific flat_down_stop constraints
        self._add_flat_down_stop_constraints(time, model, parameters)

        # Reserve constraints (if not already added by component methods)
        self._add_reserve_constraints(time, model, parameters)

        # Shutdown gradient constraints
        self._add_shutdown_gradient_constraints(time, model, parameters)

    def _add_combination_6_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 6: T_stop = 0, T_start >= 1, T_stable >= 1."""
        # Combines START and ON_FLAT states
        self._add_combination_3_constraints(time, model, parameters)
        self._add_combination_4_constraints(time, model, parameters)

        # Additional reserve and gradient constraints for this combination
        self._add_reserve_constraints(time, model, parameters)
        self._add_complete_gradient_constraints(time, model, parameters)
        self._add_daily_energy_constraints(time, model, parameters)

    def _add_combination_7_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 7: T_stop >= 1, T_start >= 1, T_stable = 0."""
        # Combines START and STOP states without FLAT

        # Get variables
        OFF = model.get_variable(f"{self.name}_OFF_{time}")
        ON_UP = model.get_variable(f"{self.name}_ON_UP_{time}")
        ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{time}")
        START = model.get_variable(f"{self.name}_START_{time}")
        STOP = model.get_variable(f"{self.name}_STOP_{time}")

        # Five-state mutual exclusion
        model.add_constraint(OFF + ON_UP + ON_DOWN + START + STOP == 1)

        # Complex startup/shutdown sequencing constraints
        self._add_eviction_constraints(time, model, parameters, "START", self._T_start)
        self._add_eviction_constraints(time, model, parameters, "STOP", self._T_stop)

        # Reserve constraints
        self._add_reserve_constraints(time, model, parameters)

        # Complete gradient constraints
        self._add_complete_gradient_constraints(time, model, parameters)

        # Daily energy constraints
        self._add_daily_energy_constraints(time, model, parameters)

        # Shutdown gradient constraints
        self._add_shutdown_gradient_constraints(time, model, parameters)

    def _add_combination_8_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 8: T_stop >= 1, T_start >= 1, T_stable >= 1 (Most complex)."""
        # All five states: OFF, ON_UP, ON_DOWN, ON_FLAT, START, STOP
        OFF = model.get_variable(f"{self.name}_OFF_{time}")
        ON_UP = model.get_variable(f"{self.name}_ON_UP_{time}")
        ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{time}")
        ON_FLAT = model.get_variable(f"{self.name}_ON_FLAT_{time}")
        START = model.get_variable(f"{self.name}_START_{time}")
        STOP = model.get_variable(f"{self.name}_STOP_{time}")

        # Six-state mutual exclusion
        model.add_constraint(OFF + ON_UP + ON_DOWN + ON_FLAT + START + STOP == 1)

        # Combine all constraint types
        self._add_eviction_constraints(time, model, parameters, "START", self._T_start)
        self._add_eviction_constraints(time, model, parameters, "STOP", self._T_stop)
        self._add_minimum_stable_constraints(time, model, parameters)
        self._add_gradient_constraints(time, model, parameters, "combination_8")

        # All advanced constraint systems for most complex combination
        self._add_reserve_constraints(time, model, parameters)
        self._add_complete_gradient_constraints(time, model, parameters)
        self._add_flat_down_stop_constraints(time, model, parameters)
        self._add_daily_energy_constraints(time, model, parameters)
        self._add_shutdown_gradient_constraints(time, model, parameters)

    def _add_minimum_time_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters, combination: str
    ):
        """Add minimum time on/off constraints."""
        time_idx = parameters.thermal_op_times.index(time)

        # Minimum time ON constraints
        if self._T_on > 0:
            turned_on = model.get_variable(f"{self.name}_turned_on_{time}")

            for k in range(1, min(self._T_on, len(parameters.thermal_op_times) - time_idx)):
                future_time = parameters.thermal_op_times[time_idx + k]
                OFF_future = model.get_variable(f"{self.name}_OFF_{future_time}")
                model.add_constraint(turned_on + OFF_future <= 1)

        # Minimum time OFF constraints
        if self._T_off > 0:
            turned_off = model.get_variable(f"{self.name}_turned_off_{time}")

            for k in range(1, min(self._T_off, len(parameters.thermal_op_times) - time_idx)):
                future_time = parameters.thermal_op_times[time_idx + k]
                OFF_future = model.get_variable(f"{self.name}_OFF_{future_time}")
                model.add_constraint(turned_off <= OFF_future)

    def _add_eviction_constraints(
        self,
        time: DateTime,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
        state_name: str,
        duration: int,
    ):
        """Add eviction constraints for START/STOP states."""
        time_idx = parameters.thermal_op_times.index(time)

        if duration > 1 and time_idx >= duration - 1:
            past_time = parameters.thermal_op_times[time_idx - (duration - 1)]
            current_state = model.get_variable(f"{self.name}_{state_name}_{time}")

            if state_name == "START":
                past_turned_on = model.get_variable(f"{self.name}_turned_on_{past_time}")
                model.add_constraint(past_turned_on + current_state <= 1)
            elif state_name == "STOP":
                past_turned_off = model.get_variable(f"{self.name}_turned_off_{past_time}")
                model.add_constraint(past_turned_off + current_state <= 1)

    def _add_minimum_stable_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Add minimum stable power duration constraints."""
        if self._T_stable > 0:
            time_idx = parameters.thermal_op_times.index(time)
            stable = model.get_variable(f"{self.name}_stable_{time}")

            for k in range(1, min(self._T_stable, len(parameters.thermal_op_times) - time_idx)):
                future_time = parameters.thermal_op_times[time_idx + k]
                ON_FLAT_future = model.get_variable(f"{self.name}_ON_FLAT_{future_time}")
                model.add_constraint(stable <= ON_FLAT_future)

    def _add_ramping_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters, combination: str
    ):
        """Add ramping/gradient constraints."""
        time_idx = parameters.thermal_op_times.index(time)
        if time_idx == 0:
            return

        prev_time = parameters.thermal_op_times[time_idx - 1]
        power_level = model.get_variable(f"{self.name}_power_level_{time}")
        prev_power_level = model.get_variable(f"{self.name}_power_level_{prev_time}")

        if self._Delta_Q > 0:  # Finite ramping rate
            turned_on = model.get_variable(f"{self.name}_turned_on_{time}")
            turned_off = model.get_variable(f"{self.name}_turned_off_{time}")

            if combination in ["combination_1", "combination_2", "combination_4", "combination_7"]:
                prev_ON_UP = model.get_variable(f"{self.name}_ON_UP_{prev_time}")
                prev_ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{prev_time}")

                # Upward ramping constraint
                model.add_constraint(
                    power_level - prev_power_level
                    <= self._Delta_Q * prev_ON_UP + self._Delta_Q_unconstrained * turned_on
                )

                # Downward ramping constraint
                model.add_constraint(
                    power_level - prev_power_level
                    >= -self._Delta_Q * prev_ON_DOWN - self._Delta_Q_unconstrained * turned_off
                )

    def _add_gradient_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters, combination: str
    ):
        """Add sophisticated gradient constraints for stable operation."""
        time_idx = parameters.thermal_op_times.index(time)
        if time_idx == 0:
            return

        prev_time = parameters.thermal_op_times[time_idx - 1]

        # Get gradient variables
        U = model.get_variable(f"{self.name}_U_{time}")
        tilde_U = model.get_variable(f"{self.name}_tilde_U_{time}")
        D = model.get_variable(f"{self.name}_D_{time}")
        tilde_D = model.get_variable(f"{self.name}_tilde_D_{time}")

        power_level = model.get_variable(f"{self.name}_power_level_{time}")
        prev_power_level = model.get_variable(f"{self.name}_power_level_{prev_time}")

        ON_UP = model.get_variable(f"{self.name}_ON_UP_{time}")
        ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{time}")
        prev_ON_UP = model.get_variable(f"{self.name}_ON_UP_{prev_time}")
        prev_ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{prev_time}")

        # Complex gradient formulation
        model.add_constraint(U == prev_ON_UP * prev_ON_UP * (power_level - prev_power_level))
        model.add_constraint(D == prev_ON_DOWN * prev_ON_DOWN * (power_level - prev_power_level))

        # Semi-continuous constraints for tilde variables
        max_power = self.maximum_power.get_value(time)
        model.add_constraint(tilde_U <= max_power * ON_UP)
        model.add_constraint(tilde_U >= -max_power * ON_UP)
        model.add_constraint(tilde_D <= max_power * ON_DOWN)
        model.add_constraint(tilde_D >= -max_power * ON_DOWN)

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        """Add objective function terms for thermal equipment."""
        if time not in parameters.thermal_op_times:
            return

        power_level = model.get_variable(f"{self.name}_power_level_{time}")

        # Variable cost (fuel, O&M)
        variable_cost = get_variable_cost(self, time)
        model.add_objective(variable_cost * power_level * parameters.timestep)

        # Startup cost
        turned_on = model.get_variable(f"{self.name}_turned_on_{time}")
        startup_cost = self.startup_cost.get_value(time)
        model.add_objective(startup_cost * turned_on)

        # Revenue from power sales (negative cost)
        if time in parameters.target_times:
            model.add_objective(-price_forecast * power_level * parameters.timestep)

        # Penalty costs for additional power variables (constraint relaxation)
        additional_above = model.get_variable(f"{self.name}_additional_power_above_{time}")
        additional_below = model.get_variable(f"{self.name}_additional_power_below_{time}")

        # High penalty cost for constraint violations
        penalty_cost = 10000.0  # €/MWh
        model.add_objective(penalty_cost * (additional_above + additional_below) * parameters.timestep)

    @model_validator(mode="after")
    def validate_minimum_stable_power_duration(self) -> ThermalPO:
        """
        Validate that minimum_stable_power_duration is not greater than minimum_time_on.
        """
        if (
            self.minimum_stable_power_duration is not None
            and self.minimum_time_on is not None
            and self.minimum_stable_power_duration.total_minutes() > self.minimum_time_on.total_minutes()
        ):
            raise ValueError(
                f"minimum_stable_power_duration ({self.minimum_stable_power_duration.total_hours()}h) of equipment "
                f"{self.name} cannot be greater than minimum_time_on ({self.minimum_time_on.total_hours()}h)"
            )
        return self

    def get_startup_cost(self, time: DateTime) -> float:
        """Get startup cost at given time."""
        return self.startup_cost.get_value(time)

    def get_reserve_procurement(self, time: DateTime, reserve_type: str, execution_date: DateTime) -> float:
        """Get reserve procurement value for given reserve type and time."""
        reserve_matrix = getattr(self, f"{reserve_type}_procured")
        return reserve_matrix.get_forecast(execution_date, time, time).get_value(time)

    def _add_reserve_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Add complete reserve constraint system from legacy code."""
        # Get reserve variables
        reserves_up = model.get_variable(f"{self.name}_reserves_up_{time}")
        reserves_down = model.get_variable(f"{self.name}_reserves_down_{time}")
        unprovided_reserves_up = model.get_variable(f"{self.name}_unprovided_reserves_up_{time}")
        unprovided_reserves_down = model.get_variable(f"{self.name}_unprovided_reserves_down_{time}")
        automated_reserves_up = model.get_variable(f"{self.name}_automated_reserves_up_{time}")
        automated_reserves_down = model.get_variable(f"{self.name}_automated_reserves_down_{time}")

        # Get state variables
        if self._combination in [1, 2, 3, 4, 5, 6, 7, 8]:
            # Power level constraint with reserves
            power_level = model.get_variable(f"{self.name}_power_level_{time}")

            # Reserve procurement constraints
            afrr_up_procured = self.afrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            afrr_down_procured = self.afrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            mfrr_up_procured = self.mfrr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            mfrr_down_procured = self.mfrr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )
            rr_up_procured = self.rr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            rr_down_procured = self.rr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            fcr_up_procured = self.fcr_up_procured.get_forecast(parameters.execution_date, time, time).get_value(time)
            fcr_down_procured = self.fcr_down_procured.get_forecast(parameters.execution_date, time, time).get_value(
                time
            )

            # Reserve balance constraints (Equation 41-44 from legacy)
            model.add_constraint(reserves_up + unprovided_reserves_up == rr_up_procured + mfrr_up_procured)
            model.add_constraint(reserves_down + unprovided_reserves_down == rr_down_procured + mfrr_down_procured)
            model.add_constraint(
                automated_reserves_up
                == min(afrr_up_procured, self.maximum_afrr) + min(fcr_up_procured, self.maximum_fcr)
            )
            model.add_constraint(
                automated_reserves_down
                == min(afrr_down_procured, self.maximum_afrr) + min(fcr_down_procured, self.maximum_fcr)
            )

            # Reserve capacity constraints
            max_power = self.maximum_power.get_value(time)
            model.add_constraint(power_level + reserves_up + automated_reserves_up <= max_power)
            model.add_constraint(power_level - reserves_down - automated_reserves_down >= 0)

    def _add_daily_energy_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Add daily energy limitation constraints (Equation 37 from legacy)."""
        if self.has_daily_energy_constraint and self.maximum_daily_energy and self.maximum_daily_energy.max() > 0:
            # Find all times in the same day
            current_day_times = [t for t in parameters.thermal_op_times if t.date() == time.date()]

            if len(current_day_times) > 1:
                # Sum power over the day
                daily_energy_expr = sum(
                    model.get_variable(f"{self.name}_power_level_{t}") * parameters.timestep for t in current_day_times
                )
                model.add_constraint(daily_energy_expr <= self.maximum_daily_energy.get_value(time))

    def _add_complete_gradient_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Add complete 2-stage gradient constraint system (Equations 27-30 from legacy)."""
        time_idx = parameters.thermal_op_times.index(time)
        if time_idx == 0 or self._T_stable < 1:
            return

        prev_time = parameters.thermal_op_times[time_idx - 1]

        # Get all gradient variables
        U = model.get_variable(f"{self.name}_U_{time}")
        tilde_U = model.get_variable(f"{self.name}_tilde_U_{time}")
        D = model.get_variable(f"{self.name}_D_{time}")
        tilde_D = model.get_variable(f"{self.name}_tilde_D_{time}")

        power_level = model.get_variable(f"{self.name}_power_level_{time}")
        prev_power_level = model.get_variable(f"{self.name}_power_level_{prev_time}")

        # State variables
        ON_UP = model.get_variable(f"{self.name}_ON_UP_{time}")
        ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{time}")
        prev_ON_UP = model.get_variable(f"{self.name}_ON_UP_{prev_time}")
        prev_ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{prev_time}")

        # Equation 27: U definition
        model.add_constraint(U <= self._Delta_Q_unconstrained * prev_ON_UP)
        model.add_constraint(U >= -self._Delta_Q_unconstrained * prev_ON_UP)
        model.add_constraint(U <= power_level - prev_power_level + self._Delta_Q_unconstrained * (1 - prev_ON_UP))
        model.add_constraint(U >= power_level - prev_power_level - self._Delta_Q_unconstrained * (1 - prev_ON_UP))

        # Equation 28: D definition
        model.add_constraint(D <= self._Delta_Q_unconstrained * prev_ON_DOWN)
        model.add_constraint(D >= -self._Delta_Q_unconstrained * prev_ON_DOWN)
        model.add_constraint(D <= power_level - prev_power_level + self._Delta_Q_unconstrained * (1 - prev_ON_DOWN))
        model.add_constraint(D >= power_level - prev_power_level - self._Delta_Q_unconstrained * (1 - prev_ON_DOWN))

        # Equation 29: tilde_U constraints
        max_power = self.maximum_power.get_value(time)
        model.add_constraint(tilde_U <= max_power * ON_UP)
        model.add_constraint(tilde_U >= -max_power * ON_UP)
        model.add_constraint(tilde_U <= U + max_power * (1 - ON_UP))
        model.add_constraint(tilde_U >= U - max_power * (1 - ON_UP))

        # Equation 30: tilde_D constraints
        model.add_constraint(tilde_D <= max_power * ON_DOWN)
        model.add_constraint(tilde_D >= -max_power * ON_DOWN)
        model.add_constraint(tilde_D <= D + max_power * (1 - ON_DOWN))
        model.add_constraint(tilde_D >= D - max_power * (1 - ON_DOWN))

        # Gradient limitation with 2-stage variables
        if self._Delta_Q > 0:
            model.add_constraint(tilde_U <= self._Delta_Q)
            model.add_constraint(tilde_D >= -self._Delta_Q)

    def _add_flat_down_stop_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Add flat_down_stop auxiliary variable constraints (Equation 22 from legacy)."""
        if self._combination not in [5, 8]:  # Only for combinations with STOP + FLAT
            return

        time_idx = parameters.thermal_op_times.index(time)
        if time_idx < 2:
            return

        flat_down_stop = model.get_variable(f"{self.name}_flat_down_stop_{time}")
        STOP = model.get_variable(f"{self.name}_STOP_{time}")

        prev_time = parameters.thermal_op_times[time_idx - 1]
        prev2_time = parameters.thermal_op_times[time_idx - 2]
        prev_ON_DOWN = model.get_variable(f"{self.name}_ON_DOWN_{prev_time}")
        prev2_ON_FLAT = model.get_variable(f"{self.name}_ON_FLAT_{prev2_time}")

        # flat_down_stop = floor((STOP + ON_DOWN[t-1] + ON_FLAT[t-2]) / 3)
        # Implemented as: 3 * flat_down_stop <= sum <= 3 * flat_down_stop + 2
        model.add_constraint(3 * flat_down_stop <= STOP + prev_ON_DOWN + prev2_ON_FLAT)
        model.add_constraint(3 * flat_down_stop >= STOP + prev_ON_DOWN + prev2_ON_FLAT - 2)

        # Additional constraints for flat_down_stop usage
        model.add_constraint(flat_down_stop <= STOP)
        model.add_constraint(flat_down_stop <= prev_ON_DOWN)
        model.add_constraint(flat_down_stop <= prev2_ON_FLAT)

    def _add_shutdown_gradient_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Add shutdown gradient constraints with q_step modifications."""
        if self._combination not in [2, 5, 7, 8]:  # Only for combinations with STOP
            return

        time_idx = parameters.thermal_op_times.index(time)
        if time_idx == 0:
            return

        STOP = model.get_variable(f"{self.name}_STOP_{time}")
        power_level = model.get_variable(f"{self.name}_power_level_{time}")

        # Shutdown gradient modification (q_step logic from legacy)
        max_power = self.maximum_power.get_value(time)

        # During shutdown, power must be between q_step bounds
        q_step_lower = 0  # Simplified - in legacy this depends on shutdown progression
        q_step_upper = max_power * 0.5  # Simplified shutdown limitation

        model.add_constraint(power_level >= q_step_lower * STOP)
        model.add_constraint(power_level <= q_step_upper * STOP + max_power * (1 - STOP))

    def get_combination_info(self) -> dict[str, Any]:
        """Get information about the constraint combination being used."""
        return {
            "combination": self._combination,
            "T_on": self._T_on,
            "T_off": self._T_off,
            "T_start": self._T_start,
            "T_stop": self._T_stop,
            "T_stable": self._T_stable,
            "Delta_Q": self._Delta_Q,
            "has_start_state": self._T_start >= 1,
            "has_stop_state": self._T_stop >= 1,
            "has_stable_state": self._T_stable >= 1,
            "automated_unsupplied_reserves": getattr(self, "_automated_unsupplied_reserves", 0),
        }
