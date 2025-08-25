"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import math

from pendulum import DateTime
from pydantic import model_validator

from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.portfolio_optimisation.models.thermal.thermal_init_conditions import ThermalInitialConditions
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
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
    # minimum_power: Timeseries | LazyTimeseries
    maximum_power: Timeseries | LazyTimeseries
    variable_cost: Timeseries | LazyTimeseries
    # startup_cost: Timeseries | LazyTimeseries
    maximum_gradient: float = 0.0  # MW/min ramping rate
    has_daily_energy_constraint: bool = False

    # Reserve procurement forecasts
    # afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    # afrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    # mfrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    # mfrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    # rr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    # rr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    # fcr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    # fcr_down_procured: ForecastingMatrix | LazyForecastingMatrix

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

        # Convert time durations to time steps
        if self.minimum_time_on and self.minimum_time_on.total_minutes() > 0:
            self._T_on = int(max(1, math.ceil(self.minimum_time_on / parameters.timestep))) + 1
        else:
            self._T_on = 0

        if self.minimum_time_off and self.minimum_time_off.total_minutes() > 0:
            self._T_off = int(max(1, math.ceil(self.minimum_time_off / parameters.timestep))) + 1
        else:
            self._T_off = 0

        if self.startup_duration:
            self._T_start = int(math.floor(self.startup_duration / parameters.timestep))
        else:
            self._T_start = 0

        if self.shutdown_duration:
            self._T_stop = int(math.floor(self.shutdown_duration / parameters.timestep))
        else:
            self._T_stop = 0

        if self.minimum_stable_power_duration:
            if self.minimum_stable_power_duration < parameters.timestep:
                self._T_stable = 0
            else:
                self._T_stable = int(math.ceil(self.minimum_stable_power_duration / parameters.timestep)) + 1
                # Rescale T_stable so that it is either equal to 0 or >= 2
                self._T_stable = self._T_stable if self._T_stable >= 2 else 0
        else:
            self._T_stable = 0

        # Ramping parameters
        self._Delta_Q = self.maximum_gradient * parameters.timestep.total_minutes()
        self._Delta_Q_unconstrained = self.maximum_power.max()

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

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """Build variables for complex thermal unit commitment."""

        self._compute_time_parameters(parameters)

        # Always defined state variables for optimization time frame
        if time in parameters.thermal_op_times:
            # Binary state variables
            model.add_boolean_variable(f"OFF_var_e_{self.name}_at_{time}")
            model.add_boolean_variable(f"ON_UP_var_e_{self.name}_at_{time}")
            model.add_boolean_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")

            # Auxiliary binary variables for transitions
            model.add_boolean_variable(f"t_on_of_e_{self.name}_at_{time}")
            model.add_boolean_variable(f"t_off_of_e_{self.name}_at_{time}")

            # Conditional state variables based on time constraints
            if self._T_start >= 1:
                model.add_boolean_variable(f"ON_START_e_{self.name}_at_{time}")

            if self._T_stop >= 1:
                model.add_boolean_variable(f"STOP_e_{self.name}_at_{time}")

            if self._T_stable >= 1:
                model.add_boolean_variable(f"ON_FLAT_e_{self.name}_at_{time}")
                model.add_boolean_variable(f"stable_at_{time}_e_{self.name}")
                model.add_boolean_variable(f"entered_up_at_{time}_e_{self.name}")
                model.add_boolean_variable(f"entered_down_at_{time}_e_{self.name}")

                # Gradient auxiliary variables for stable case
                max_power = self.maximum_power.max()
                model.add_continuous_variable(f"UP_grad_at_{time}_for_e_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"aux_up_grad_at_{time}_e_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"DOWN_grad_at_{time}_e_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"aux_down_grad_at_{time}_e_{self.name}", -max_power, max_power)

            # Specific combinations for additional auxiliary variables
            if self._T_stop >= 1 and self._T_start == 0 and self._T_stable == 0:
                model.add_boolean_variable(f"down_to_stop_grad_at_{time}_e_{self.name}")

            if self._T_stop >= 1 and self._T_stable >= 1:
                model.add_boolean_variable(f"flat_down_stop_at_{time}_e_{self.name}")

            if self._T_stable >= 1 and (self._T_start >= 1 or self._T_stop >= 1):
                max_power = self.maximum_power.max()
                model.add_continuous_variable(f"DD_grad_at_{time}_e_{self.name}", -max_power, max_power)

            if self._T_stop >= 1 and self._T_start >= 1 and self._T_stable == 0:
                model.add_boolean_variable(f"down_to_stop_grad_at_{time}_e_{self.name}")

            # Power and reserve variables
            maximum_power = self.maximum_power.get_value(time)
            minimum_power = self.minimum_power.get_value(time)
            maximum_automated = get_maximum_automated(self)

            # Power level variable (only for thermal optimization times)
            model.add_continuous_variable(f"{self.name}_p_lev_{time}", 0.0, maximum_power)
            model.add_continuous_variable(f"{self.name}_p_lev_above_maxAvail_{time}", 0.0, maximum_power)
            model.add_continuous_variable(f"{self.name}_p_lev_below_minAvail_{time}", 0.0, maximum_power)

            # Reserve variables using utility function
            # This creates: reserves_up_{name}_{time}, reserves_down_{name}_{time}, etc.
            add_reserve_variables(
                model=model,
                name=self.name,
                time=time,
                min_power=minimum_power,
                max_power=maximum_power,
                maximum_automated=maximum_automated,
                relaxed_reserves=True,
                storage_equipment=False,
                thermal_equipment=True,
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

        if not hasattr(self, "_initial_conditions_added"):
            self.add_initial_conditions(model, parameters)
            self._initial_conditions_added = True

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

        # Variable cost term: cost * power * time_step / 60
        variable_cost = self.variable_cost.get_value(time)
        power_level_var = model.get_variable(f"{self.name}_p_lev_{time}")
        model.add_objective(variable_cost * power_level_var * parameters.timestep.total_hours(), "minimize")

        if len(parameters.target_times) > 0 and time not in parameters.target_times:
            model.add_objective(-price_forecast * power_level_var * parameters.timestep.total_hours(), "minimize")

        # Startup cost term: startup_cost * turned_on
        startup_cost = self.startup_cost.get_value(time)
        turned_on_var = model.get_variable(f"t_on_of_e_{self.name}_at_{time}")
        model.add_objective(startup_cost * turned_on_var, "minimize")

    def _add_combination_1_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 1: T_stop = T_stable = T_start = 0"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.name}_at_{time}")
        power_level_var = model.get_variable(f"{self.name}_p_lev_{time}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.name}_{time}")

        # Power bounds
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on (sec. 6.1.1)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (sec. 6.1.2)
        model.add_constraint(turned_off_var <= 1 - off_prev_var)
        model.add_constraint(turned_off_var <= off_var)
        model.add_constraint(turned_off_var >= off_var - off_prev_var)

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint
        model.add_constraint(off_var + on_up_var + on_down_var == 1)

        # Minimum time on and off constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        # C. CONSTRAINTS ON THE CONTROL VARIABLE

        # Reserve "fill up" constraints

        # Upward constraint
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            <= q_upper + parameters.allowed_round_off_error
        )
        model.add_constraint(
            power_level_var + reserves_up_var + automated_reserves_up_var + unprovided_reserves_up_var
            >= q_upper - parameters.allowed_round_off_error
        )

        # Downward constraint
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

        # Reserve availability constraints
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var))
        model.add_constraint(reserves_up_var <= q_upper * (1 - off_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - off_var))

        # Power output bounds
        model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var))
        model.add_constraint(power_level_var <= q_upper * (on_up_var + on_down_var))

        # Power gradients (if not the last time step)
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * on_up_prev_var + self._Delta_Q_unconstrained * turned_on_var
                )
                # Downward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * on_down_prev_var - self._Delta_Q_unconstrained * turned_off_var
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * on_up_prev_var + self._Delta_Q_unconstrained * turned_on_var
                )
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * on_down_prev_var - self._Delta_Q_unconstrained * turned_off_var
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def _add_combination_2_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 2: T_stop >= 1, T_stable = T_start = 0"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")
        stop_var = model.get_variable(f"STOP_e_{self.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.name}_at_{time}")
        down_to_stop_var = model.get_variable(f"down_to_stop_grad_at_{time}_e_{self.name}")
        power_level_var = model.get_variable(f"{self.name}_p_lev_{time}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{prev_time}")
        stop_prev_var = model.get_variable(f"STOP_e_{self.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.name}_{time}")

        # Power bounds and parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Shutdown gradient parameters
        q_min = self.minimum_power.max()  # Get the minimum power without reserve requirements
        q_step = q_min / self._T_stop

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
        if self._T_stop > 1:
            eviction_time = time - (self._T_stop - 1) * parameters.timestep
            turned_off_eviction_var = model.get_variable(f"t_off_of_e_{self.name}_at_{eviction_time}")
            model.add_constraint(turned_off_eviction_var + stop_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                local_time = time - (s + self._T_stop) * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        # Shutdown ramp constraints
        if self._T_stop >= 2:
            for s in range(1, self._T_stop - 1):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
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
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * on_up_prev_var
                    - turned_off_var * q_step
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                # Downward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * on_down_prev_var
                    - turned_off_var * q_step
                    - stop_prev_var * q_step
                    + down_to_stop_var * self._Delta_Q
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * on_up_prev_var
                    - turned_off_var * q_step
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * on_down_prev_var
                    - turned_off_var * q_step
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * down_to_stop_var
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def _add_combination_3_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 3: T_stop = 0, T_start = 0, T_stable >= 1"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")
        on_flat_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.name}_at_{time}")
        stable_var = model.get_variable(f"stable_at_{time}_e_{self.name}")
        entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.name}")
        entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.name}")
        power_level_var = model.get_variable(f"{self.name}_p_lev_{time}")

        # Gradient auxiliary variables
        up_grad_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.name}")
        aux_up_grad_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.name}")
        down_grad_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.name}")
        aux_down_grad_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.name}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{prev_time}")
        on_flat_prev_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.name}_{time}")

        # Power bounds
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

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
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        if self._T_stable >= 2:
            for s in range(1, self._T_stable - 1):
                local_time = time - s * parameters.timestep
                stable_local_var = model.get_variable(f"stable_at_{local_time}_e_{self.name}")
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
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * entered_up_var
                    + up_grad_var
                    + down_grad_var
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                # Downward gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * entered_down_var
                    + up_grad_var
                    + down_grad_var
                    - self._Delta_Q_unconstrained * turned_off_var
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * entered_up_var
                    + up_grad_var
                    + down_grad_var
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * entered_down_var
                    + up_grad_var
                    + down_grad_var
                    - self._Delta_Q_unconstrained * turned_off_var
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def _add_combination_4_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 4: T_start >= 1, T_stable = T_stop = 0"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")
        start_var = model.get_variable(f"ON_START_e_{self.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.name}_at_{time}")
        power_level_var = model.get_variable(f"{self.name}_p_lev_{time}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{prev_time}")
        start_prev_var = model.get_variable(f"ON_START_e_{self.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.name}_{time}")

        # Power bounds and startup parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Startup gradient parameters
        q_min = self.minimum_power.max()  # Get the minimum power without reserve requirements
        q_step = q_min / self._T_start

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on (entering START state) - eq. (3)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (entering OFF state) - eq. (4)
        # Since T_stop = 0, turned_off is when entering OFF directly
        model.add_constraint(turned_off_var <= 1 - off_prev_var)
        model.add_constraint(turned_off_var <= off_var)
        model.add_constraint(turned_off_var >= off_var - off_prev_var)

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - includes START state - eq. (11)
        model.add_constraint(off_var + on_up_var + on_down_var + start_var == 1)

        # Transition constraints
        # Transitions from ON_UP and ON_DOWN to START are forbidden - eq. (12)
        model.add_constraint(on_up_prev_var + start_var <= 1)
        model.add_constraint(on_down_prev_var + start_var <= 1)

        # Transition from START to OFF is forbidden - eq. (13)
        model.add_constraint(start_prev_var + off_var <= 1)

        # Direct transitions from OFF to ON_UP and ON_DOWN are forbidden - eq. (17)
        model.add_constraint(off_prev_var + on_up_var <= 1)
        model.add_constraint(off_prev_var + on_down_var <= 1)

        # Eviction constraint - forces unit to leave START state once startup is finished - eq. (16)
        if self._T_start >= 1:
            eviction_time = time - (self._T_start - 1) * parameters.timestep
            turned_on_eviction_var = model.get_variable(f"t_on_of_e_{self.name}_at_{eviction_time}")
            model.add_constraint(turned_on_eviction_var + start_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (27) with T_start > 0 - adjusted timing for startup
                local_time = time - (s + self._T_start) * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        # Startup ramp constraints - if T_start >= 2, enforce startup sequence
        if self._T_start >= 2:
            for s in range(1, self._T_start):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
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

        # Relaxed reserve disabling condition - only available when ON_UP or ON_DOWN
        model.add_constraint(relaxed_reserves_var <= q_lower * (1 - on_up_var - on_down_var))

        # Reserve availability constraints - no reserves during OFF or START states
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var))
        model.add_constraint(reserves_up_var <= q_upper * (1 - off_var - start_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - off_var - start_var))

        # Power output bounds
        # Lower bound - only for operational states (not START)
        model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var))

        # Upper bound - includes startup ramping capability
        model.add_constraint(power_level_var <= q_upper * (on_up_var + on_down_var) + start_var * q_min)

        # Power gradients with startup considerations
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient with startup ramping - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * on_up_prev_var + turned_on_var * q_step + start_prev_var * q_step
                )
                # Downward gradient with startup ramping - eq. (35)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * on_down_prev_var
                    + turned_on_var * q_step
                    + start_prev_var * q_step
                    - self._Delta_Q_unconstrained * turned_off_var
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient with startup ramping - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * on_up_prev_var + turned_on_var * q_step + start_prev_var * q_step
                )
                # Downward unconstrained gradient with startup ramping - eq. (36)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * on_down_prev_var
                    + turned_on_var * q_step
                    + start_prev_var * q_step
                    - self._Delta_Q_unconstrained * turned_off_var
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def _add_combination_5_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 5: T_start = 0, T_stable >= 1, T_stop >= 1"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")
        on_flat_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{time}")
        stop_var = model.get_variable(f"STOP_e_{self.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.name}_at_{time}")
        stable_var = model.get_variable(f"stable_at_{time}_e_{self.name}")
        entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.name}")
        entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.name}")
        flat_down_stop_var = model.get_variable(f"flat_down_stop_at_{time}_e_{self.name}")
        power_level_var = model.get_variable(f"{self.name}_p_lev_{time}")

        # Gradient auxiliary variables
        up_grad_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.name}")
        aux_up_grad_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.name}")
        down_grad_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.name}")
        aux_down_grad_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.name}")
        dd_grad_var = model.get_variable(f"DD_grad_at_{time}_e_{self.name}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{prev_time}")
        on_flat_prev_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{prev_time}")
        stop_prev_var = model.get_variable(f"STOP_e_{self.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.name}_p_lev_{prev_time}")
        down_grad_prev_var = model.get_variable(f"DOWN_grad_at_{prev_time}_e_{self.name}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.name}_{time}")

        # Power bounds and shutdown parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Shutdown gradient parameters
        q_min = self.minimum_power.max()
        q_step = q_min / self._T_stop

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
        on_flat_two_prev_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{two_steps_ago}")
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
            model.add_constraint(dd_grad_var <= q_upper * stop_var)
            model.add_constraint(dd_grad_var >= q_lower * stop_var)
            model.add_constraint(dd_grad_var <= down_grad_prev_var - q_lower * (1 - stop_var))
            model.add_constraint(dd_grad_var >= down_grad_prev_var - q_upper * (1 - stop_var))

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - 5 states - eq. (9)
        model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var + stop_var == 1)

        # Transition constraints - eq. (25)
        # UP-DOWN and DOWN-UP transitions are forbidden
        model.add_constraint(on_up_prev_var + on_down_var <= 1)
        model.add_constraint(on_down_prev_var + on_up_var <= 1)
        # ON_XX to OFF transitions are forbidden
        model.add_constraint(on_up_prev_var + off_var <= 1)
        model.add_constraint(on_down_prev_var + off_var <= 1)

        # STOP to ON transitions are forbidden - eq. (13)
        model.add_constraint(stop_prev_var + on_flat_var <= 1)
        model.add_constraint(stop_prev_var + on_down_var <= 1)
        model.add_constraint(stop_prev_var + on_up_var <= 1)

        # ON_UP to STOP transition is forbidden - eq. (21)
        model.add_constraint(on_up_prev_var + stop_var <= 1)
        # OFF to STOP transition is forbidden - eq. (12)
        model.add_constraint(off_prev_var + stop_var <= 1)

        # Eviction constraint - unit must leave STOP state after T_stop time steps - eq. (19)
        if self._T_stop > 1:
            eviction_time = time - (self._T_stop - 1) * parameters.timestep
            turned_off_eviction_var = model.get_variable(f"t_off_of_e_{self.name}_at_{eviction_time}")
            model.add_constraint(turned_off_eviction_var + stop_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (31) with T_start = 0
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                # eq. (32) with T_stop > 0 - adjusted timing for shutdown
                local_time = time - (s + self._T_stop) * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        if self._T_stable >= 2:
            for s in range(1, self._T_stable - 1):
                # eq. (26)
                local_time = time - s * parameters.timestep
                stable_local_var = model.get_variable(f"stable_at_{local_time}_e_{self.name}")
                model.add_constraint(stable_local_var <= on_flat_var)

        # Shutdown ramp constraints - eq. (24)
        if self._T_stop >= 2:
            for s in range(1, self._T_stop - 1):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
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
        # Manual reserves only available in FLAT state
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

        # Power gradients with complex auxiliary variables
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * entered_up_var
                    + up_grad_var
                    + down_grad_var
                    - q_step * turned_off_var
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * turned_on_var
                    - dd_grad_var
                )
                # Downward gradient - eq. (35)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * entered_down_var
                    + up_grad_var
                    + down_grad_var
                    - q_step * turned_off_var
                    - stop_prev_var * q_step
                    + flat_down_stop_var * self._Delta_Q
                    - dd_grad_var
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * entered_up_var
                    + up_grad_var
                    + down_grad_var
                    - q_step * turned_off_var
                    - stop_prev_var * q_step
                    + self._Delta_Q_unconstrained * turned_on_var
                )
                # Downward unconstrained gradient - eq. (36)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * entered_down_var
                    + up_grad_var
                    + down_grad_var
                    - q_step * turned_off_var
                    - stop_prev_var * q_step
                    + flat_down_stop_var * self._Delta_Q_unconstrained
                    - dd_grad_var
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def _add_combination_6_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 6: T_stop = 0, T_stable >= 1, T_start >= 1"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")
        on_flat_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{time}")
        start_var = model.get_variable(f"ON_START_e_{self.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.name}_at_{time}")
        stable_var = model.get_variable(f"stable_at_{time}_e_{self.name}")
        entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.name}")
        entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.name}")
        power_level_var = model.get_variable(f"{self.name}_p_lev_{time}")

        # Gradient auxiliary variables
        up_grad_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.name}")
        aux_up_grad_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.name}")
        down_grad_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.name}")
        aux_down_grad_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.name}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{prev_time}")
        on_flat_prev_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{prev_time}")
        start_prev_var = model.get_variable(f"ON_START_e_{self.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.name}_p_lev_{prev_time}")
        up_grad_prev_var = model.get_variable(f"UP_grad_at_{prev_time}_for_e_{self.name}")
        down_grad_prev_var = model.get_variable(f"DOWN_grad_at_{prev_time}_e_{self.name}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.name}_{time}")

        # Power bounds and startup parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Startup gradient parameters
        q_min = self.minimum_power.max()
        q_step = q_min / self._T_start

        # A. CONSTRAINTS ON THE AUXILIARY VARIABLES

        # Constraints on turned_on - eq. (3)
        model.add_constraint(turned_on_var <= 1 - off_var)
        model.add_constraint(turned_on_var <= off_prev_var)
        model.add_constraint(turned_on_var >= off_prev_var - off_var)

        # Constraints on turned_off (entering OFF state directly) - eq. (4)
        # Since T_stop = 0, turned_off is when entering OFF directly
        model.add_constraint(turned_off_var <= 1 - off_prev_var)
        model.add_constraint(turned_off_var <= off_var)
        model.add_constraint(turned_off_var >= off_var - off_prev_var)

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

        # B. CONSTRAINTS ON THE STATE VARIABLES

        # Mutual exclusion constraint - 5 states - eq. (9)
        model.add_constraint(off_var + on_up_var + on_down_var + on_flat_var + start_var == 1)

        # Transition constraints - eq. (25)
        # UP-DOWN and DOWN-UP transitions are forbidden
        model.add_constraint(on_up_prev_var + on_down_var <= 1)
        model.add_constraint(on_down_prev_var + on_up_var <= 1)

        # Constraints involving START and OFF - eq. (10)
        model.add_constraint(on_up_prev_var + start_var <= 1)
        model.add_constraint(on_down_prev_var + start_var <= 1)
        model.add_constraint(on_flat_prev_var + start_var <= 1)

        # START to OFF transition is forbidden - eq. (11)
        model.add_constraint(start_prev_var + off_var <= 1)

        # Direct transitions from OFF to operational states are forbidden - eq. (15)
        model.add_constraint(off_prev_var + on_up_var <= 1)
        model.add_constraint(off_prev_var + on_down_var <= 1)
        model.add_constraint(off_prev_var + on_flat_var <= 1)

        # Eviction constraint - forces unit to leave START state after T_start time steps - eq. (16)
        if self._T_start >= 1:
            eviction_time = time - (self._T_start - 1) * parameters.timestep
            turned_on_eviction_var = model.get_variable(f"t_on_of_e_{self.name}_at_{eviction_time}")
            model.add_constraint(turned_on_eviction_var + start_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (31) with T_start > 0 - adjusted timing for startup
                local_time = time - (s + self._T_start) * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                # eq. (32) with T_stop = 0
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        if self._T_stable >= 2:
            for s in range(1, self._T_stable - 1):
                # eq. (26)
                local_time = time - s * parameters.timestep
                stable_local_var = model.get_variable(f"stable_at_{local_time}_e_{self.name}")
                model.add_constraint(stable_local_var <= on_flat_var)

        # Startup ramp constraints - eq. (17)
        if self._T_start >= 2:
            for s in range(1, self._T_start):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
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
        model.add_constraint(automated_reserves_up_var <= maximum_automated * (1 - off_var - start_var))
        model.add_constraint(automated_reserves_down_var <= maximum_automated * (1 - off_var - start_var))
        # Manual reserves only available in FLAT state (not during ramping or startup)
        model.add_constraint(reserves_up_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var))
        model.add_constraint(reserves_down_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var))

        # Power output bounds
        # Lower bound - only for operational states (not START)
        model.add_constraint(power_level_var >= q_lower * (on_up_var + on_down_var + on_flat_var))
        # Upper bound - includes startup ramping capability
        model.add_constraint(power_level_var <= q_upper * (on_up_var + on_down_var + on_flat_var) + start_var * q_min)

        # Power gradients with startup considerations and gradient auxiliary variables
        if time in parameters.thermal_op_times[:-1]:  # Not the last time step
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient with startup ramping - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * entered_up_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    + q_step * turned_on_var
                    + start_prev_var * q_step
                )
                # Downward gradient with startup ramping - eq. (35)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * entered_down_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - self._Delta_Q_unconstrained * turned_off_var
                    + q_step * turned_on_var
                    + start_prev_var * q_step
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient with startup ramping - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * entered_up_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    + q_step * turned_on_var
                    + start_prev_var * q_step
                )
                # Downward unconstrained gradient with startup ramping - eq. (36)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * entered_down_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - self._Delta_Q_unconstrained * turned_off_var
                    + q_step * turned_on_var
                    + start_prev_var * q_step
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def _add_combination_7_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 7: T_stop >= 1, T_stable = 0, T_start >= 1"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")
        start_var = model.get_variable(f"ON_START_e_{self.name}_at_{time}")
        stop_var = model.get_variable(f"STOP_e_{self.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.name}_at_{time}")
        down_to_stop_var = model.get_variable(f"down_to_stop_grad_at_{time}_e_{self.name}")
        power_level_var = model.get_variable(f"{self.name}_p_lev_{time}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{prev_time}")
        start_prev_var = model.get_variable(f"ON_START_e_{self.name}_at_{prev_time}")
        stop_prev_var = model.get_variable(f"STOP_e_{self.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.name}_p_lev_{prev_time}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.name}_{time}")

        # Power bounds and gradient parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Dual gradient parameters for startup and shutdown
        q_min = self.minimum_power.max()
        q_step_up = q_min / self._T_start  # Startup gradient step
        q_step_down = q_min / self._T_stop  # Shutdown gradient step

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
        if self._T_start >= 1:
            start_eviction_time = time - (self._T_start - 1) * parameters.timestep
            turned_on_start_eviction_var = model.get_variable(f"t_on_of_e_{self.name}_at_{start_eviction_time}")
            model.add_constraint(turned_on_start_eviction_var + start_var <= 1)

        # STOP eviction - forces unit to leave STOP state after T_stop time steps - eq. (19)
        if self._T_stop > 1:
            stop_eviction_time = time - (self._T_stop - 1) * parameters.timestep
            turned_off_stop_eviction_var = model.get_variable(f"t_off_of_e_{self.name}_at_{stop_eviction_time}")
            model.add_constraint(turned_off_stop_eviction_var + stop_var <= 1)

        # Minimum time constraints
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (27) with T_start > 0 - adjusted timing for startup
                local_time = time - (s + self._T_start) * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                # eq. (28) with T_stop > 0 - adjusted timing for shutdown
                local_time = time - (s + self._T_stop) * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        # Shutdown ramp constraints - eq. (19)
        if self._T_stop >= 2:
            for s in range(1, self._T_stop - 1):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= stop_var)

        # Startup ramp constraints - eq. (18)
        if self._T_start >= 2:
            for s in range(1, self._T_start):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
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
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * on_up_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )
                # Downward gradient - eq. (35)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q * on_down_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + down_to_stop_var * self._Delta_Q
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * on_up_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )
                # Downward unconstrained gradient - eq. (36)
                model.add_constraint(
                    power_level_var - power_prev_var
                    >= -self._Delta_Q_unconstrained * on_down_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + down_to_stop_var * self._Delta_Q_unconstrained
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def _add_combination_8_constraints(
        self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters
    ):
        """Combination 8: T_start >= 1, T_stable >= 1, T_stop >= 1"""
        prev_time = time - parameters.timestep

        # Get variables
        off_var = model.get_variable(f"OFF_var_e_{self.name}_at_{time}")
        on_up_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{time}")
        on_down_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{time}")
        on_flat_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{time}")
        start_var = model.get_variable(f"ON_START_e_{self.name}_at_{time}")
        stop_var = model.get_variable(f"STOP_e_{self.name}_at_{time}")
        turned_on_var = model.get_variable(f"t_on_of_e_{self.name}_at_{time}")
        turned_off_var = model.get_variable(f"t_off_of_e_{self.name}_at_{time}")
        stable_var = model.get_variable(f"stable_at_{time}_e_{self.name}")
        entered_up_var = model.get_variable(f"entered_up_at_{time}_e_{self.name}")
        entered_down_var = model.get_variable(f"entered_down_at_{time}_e_{self.name}")
        flat_down_stop_var = model.get_variable(f"flat_down_stop_at_{time}_e_{self.name}")
        power_level_var = model.get_variable(f"{self.name}_p_lev_{time}")

        # Gradient auxiliary variables
        up_grad_var = model.get_variable(f"UP_grad_at_{time}_for_e_{self.name}")
        aux_up_grad_var = model.get_variable(f"aux_up_grad_at_{time}_e_{self.name}")
        down_grad_var = model.get_variable(f"DOWN_grad_at_{time}_e_{self.name}")
        aux_down_grad_var = model.get_variable(f"aux_down_grad_at_{time}_e_{self.name}")

        # Previous time variables
        off_prev_var = model.get_variable(f"OFF_var_e_{self.name}_at_{prev_time}")
        on_up_prev_var = model.get_variable(f"ON_UP_var_e_{self.name}_at_{prev_time}")
        on_down_prev_var = model.get_variable(f"ON_DOWN_var_e_{self.name}_at_{prev_time}")
        on_flat_prev_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{prev_time}")
        start_prev_var = model.get_variable(f"ON_START_e_{self.name}_at_{prev_time}")
        stop_prev_var = model.get_variable(f"STOP_e_{self.name}_at_{prev_time}")
        power_prev_var = model.get_variable(f"{self.name}_p_lev_{prev_time}")
        up_grad_prev_var = model.get_variable(f"UP_grad_at_{prev_time}_for_e_{self.name}")
        down_grad_prev_var = model.get_variable(f"DOWN_grad_at_{prev_time}_e_{self.name}")
        dd_grad_prev_var = model.get_variable(f"DD_grad_at_{prev_time}_e_{self.name}")

        # Reserve variables
        reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
        reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")
        automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
        automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
        unprovided_reserves_up_var = model.get_variable(f"unprovided_reserves_up_{self.name}_{time}")
        unprovided_reserves_down_var = model.get_variable(f"unprovided_reserves_down_{self.name}_{time}")
        relaxed_reserves_var = model.get_variable(f"relaxed_reserves_{self.name}_{time}")

        # Power bounds and gradient parameters
        q_upper = self.maximum_power.get_value(time)
        q_lower = self.minimum_power.get_value(time)
        maximum_automated = get_maximum_automated(self)

        # Dual gradient parameters for startup and shutdown
        q_min = self.minimum_power.max()
        q_step_up = q_min / self._T_start  # Startup gradient step
        q_step_down = q_min / self._T_stop  # Shutdown gradient step

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
        on_flat_two_prev_var = model.get_variable(f"ON_FLAT_e_{self.name}_at_{two_steps_ago}")
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
        if self._T_stop > 1:
            stop_eviction_time = time - (self._T_stop - 1) * parameters.timestep
            turned_off_stop_eviction_var = model.get_variable(f"t_off_of_e_{self.name}_at_{stop_eviction_time}")
            model.add_constraint(turned_off_stop_eviction_var + stop_var <= 1)

        # START eviction - forces unit to leave START state after T_start time steps - eq. (16)
        if self._T_start >= 1:
            start_eviction_time = time - (self._T_start - 1) * parameters.timestep
            turned_on_start_eviction_var = model.get_variable(f"t_on_of_e_{self.name}_at_{start_eviction_time}")
            model.add_constraint(turned_on_start_eviction_var + start_var <= 1)

        # Minimum time constraints with all adjustments
        if self._T_on >= 2:
            for s in range(1, self._T_on):
                # eq. (31) with T_start > 0 - adjusted timing for startup
                local_time = time - (s + self._T_start) * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_on_local_var <= on_up_var + on_down_var + on_flat_var)

        if self._T_off >= 2:
            for s in range(1, self._T_off):
                # eq. (32) with T_stop > 0 - adjusted timing for shutdown
                local_time = time - (s + self._T_stop) * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= off_var)

        if self._T_stable >= 2:
            for s in range(1, self._T_stable - 1):
                # eq. (26)
                local_time = time - s * parameters.timestep
                stable_local_var = model.get_variable(f"stable_at_{local_time}_e_{self.name}")
                model.add_constraint(stable_local_var <= on_flat_var)

        # Shutdown ramp constraints - eq. (24)
        if self._T_stop >= 2:
            for s in range(1, self._T_stop - 1):
                local_time = time - s * parameters.timestep
                turned_off_local_var = model.get_variable(f"t_off_of_e_{self.name}_at_{local_time}")
                model.add_constraint(turned_off_local_var <= stop_var)

        # Startup ramp constraints - eq. (17)
        if self._T_start >= 2:
            for s in range(1, self._T_start):
                local_time = time - s * parameters.timestep
                turned_on_local_var = model.get_variable(f"t_on_of_e_{self.name}_at_{local_time}")
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
        model.add_constraint(
            reserves_up_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var - stop_var)
        )
        model.add_constraint(
            reserves_down_var <= q_upper * (1 - on_up_var - on_down_var - off_var - start_var - stop_var)
        )

        # Power output bounds with all ramping capabilities - eq. (29) and (30)
        # Lower bound with shutdown ramping
        model.add_constraint(
            power_level_var
            >= q_lower * (on_up_var + on_down_var + on_flat_var) + turned_off_var * (q_min - q_step_down)
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
            if self._Delta_Q > 0:  # Finite gradient
                # Upward gradient - eq. (33)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q * entered_up_var
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
                    >= -self._Delta_Q * entered_down_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + flat_down_stop_var * self._Delta_Q
                    - dd_grad_prev_var
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )
            elif self._Delta_Q == 0:  # Infinite gradient
                # Upward unconstrained gradient - eq. (34)
                model.add_constraint(
                    power_level_var - power_prev_var
                    <= self._Delta_Q_unconstrained * entered_up_var
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
                    >= -self._Delta_Q_unconstrained * entered_down_var
                    + up_grad_prev_var
                    + down_grad_prev_var
                    - turned_off_var * q_step_down
                    - stop_prev_var * q_step_down
                    + flat_down_stop_var * self._Delta_Q_unconstrained
                    - dd_grad_prev_var
                    + turned_on_var * q_step_up
                    + start_prev_var * q_step_up
                )

        # Daily energy constraints (if applicable)
        if self.has_daily_energy_constraint:
            # This would need to be implemented at a higher level since it requires all time steps for a day
            pass

    def add_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        Add initial conditions for thermal unit based on power history.

        Args:
            model: Optimization model
            parameters: Portfolio optimization parameters
            power_history: Historical power data for initial conditions (None for dayZero)
        """

        self._compute_time_parameters(parameters)

        # Create initial condition time frame
        T_traceback = max(self._T_on + self._T_start, self._T_off + self._T_stop)
        initial_times: list[DateTime] = []

        if T_traceback > 0:
            for k in range(T_traceback, 0, -1):
                initial_times.append(parameters.start_date - k * parameters.timestep)
        else:
            initial_times.append(parameters.start_date - parameters.timestep)

        power_history = self.power.get_forecast(parameters.execution_date, initial_times[0], initial_times[-1])
        extended_start_date = initial_times[0]

        # Determine if this is dayZero initialization
        day_zero = power_history is None
        if power_history is not None:
            last_time = parameters.start_date - parameters.timestep
            if last_time not in power_history.time_index:
                day_zero = True

        # Add initial condition constraints based on combination using mapping
        thermal_initial_conditions = ThermalInitialConditions(self)
        initial_condition_methods = {
            1: thermal_initial_conditions.add_combination_1_initial_conditions,
            2: thermal_initial_conditions.add_combination_2_initial_conditions,
            3: thermal_initial_conditions.add_combination_3_initial_conditions,
            4: thermal_initial_conditions.add_combination_4_initial_conditions,
            5: thermal_initial_conditions.add_combination_5_initial_conditions,
            6: thermal_initial_conditions.add_combination_6_initial_conditions,
            7: thermal_initial_conditions.add_combination_7_initial_conditions,
            8: thermal_initial_conditions.add_combination_8_initial_conditions,
        }

        method = initial_condition_methods.get(
            self._combination, thermal_initial_conditions.add_combination_1_initial_conditions
        )
        method(model, parameters, initial_times, extended_start_date, power_history, day_zero)

    @model_validator(mode="after")
    def validate_minimum_stable_power_duration(self) -> ThermalPO:
        """
        Validate that minimum_stable_power_duration is not greater than minimum_time_on.
        """
        if (
            self.minimum_stable_power_duration is not None
            and self.minimum_time_on is not None
            and self.minimum_stable_power_duration > self.minimum_time_on
        ):
            raise ValueError(
                f"minimum_stable_power_duration ({self.minimum_stable_power_duration.total_hours()}h) of equipment "
                f"{self.name} cannot be greater than minimum_time_on ({self.minimum_time_on.total_hours()}h)"
            )
        return self
