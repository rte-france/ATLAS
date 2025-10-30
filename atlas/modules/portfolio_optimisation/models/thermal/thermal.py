"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from pendulum import DateTime, Duration
from pydantic import model_validator

import atlas.config as cfg
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.portfolio_optimisation.models.thermal import (
    combination_1,
    combination_2,
    combination_3,
    combination_4,
    combination_5,
    combination_6,
    combination_7,
    combination_8,
)
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes


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
    T_traceback: int = 0

    optimisation_time_window: list[DateTime] = []

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

        # Always defined state variables for optimization time frame
        if time in self.optimisation_time_window:
            if time == self.optimisation_time_window[0]:
                if self._T_stable >= 1:
                    model.add_boolean_variable(f"ON_FLAT_{self.name}_{time - parameters.timestep}")
                    model.add_boolean_variable(f"stable_{time - parameters.timestep}_{self.name}")

            # Binary state variables
            model.add_boolean_variable(f"OFF_var_{self.name}_{time}")
            model.add_boolean_variable(f"ON_UP_var_{self.name}_{time}")
            model.add_boolean_variable(f"ON_DOWN_var_{self.name}_{time}")

            # Auxiliary binary variables for transitions
            model.add_boolean_variable(f"t_on_of_{self.name}_{time}")
            model.add_boolean_variable(f"t_off_of_{self.name}_{time}")

            # Conditional state variables based on time constraints
            if self._T_start >= 1:
                model.add_boolean_variable(f"ON_START_{self.name}_{time}")

            if self._T_stop >= 1:
                model.add_boolean_variable(f"STOP_{self.name}_{time}")

            if self._T_stable >= 1:
                model.add_boolean_variable(f"ON_FLAT_{self.name}_{time}")
                model.add_boolean_variable(f"stable_{time}_{self.name}")
                model.add_boolean_variable(f"entered_up_{time}_{self.name}")
                model.add_boolean_variable(f"entered_down_{time}_{self.name}")

                # Gradient auxiliary variables for stable case
                max_power = self.maximum_power.max()
                model.add_continuous_variable(f"UP_grad_{time}_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"aux_up_grad_{time}_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"DOWN_grad_{time}_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"aux_down_grad_{time}_{self.name}", -max_power, max_power)

            # Specific combinations for additional auxiliary variables
            if self._T_stop >= 1 and self._T_start == 0 and self._T_stable == 0:
                model.add_boolean_variable(f"down_to_stop_grad_{time}_{self.name}")

            if self._T_stop >= 1 and self._T_stable >= 1:
                model.add_boolean_variable(f"flat_down_stop_{time}_{self.name}")

            if self._T_stable >= 1 and (self._T_start >= 1 or self._T_stop >= 1):
                max_power = self.maximum_power.max()
                model.add_continuous_variable(f"DD_grad_{time}_{self.name}", -max_power, max_power)

            if self._T_stop >= 1 and self._T_start >= 1 and self._T_stable == 0:
                model.add_boolean_variable(f"down_to_stop_grad_{time}_{self.name}")

            # Power and reserve variables
            maximum_power = self.maximum_power.get_value(time)
            if self.minimum_power is None:
                self.minimum_power = Timeseries.from_index(
                    start_date=self.optimisation_time_window[0],
                    end_date=self.optimisation_time_window[-1],
                    frequency=parameters.timestep,
                    default_value=0,
                )
            minimum_power = self.minimum_power.get_value(time)
            maximum_automated = get_maximum_automated(self)

            # Power level variable (only for thermal optimization times)
            model.add_continuous_variable(f"{self.name}_power_level_{time}", 0.0, maximum_power)

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
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        """Add constraints based on the determined combination."""
        if time not in self.optimisation_time_window:
            return

        constraint_functions = {
            1: combination_1.add_constraints,
            2: combination_2.add_constraints,
            3: combination_3.add_constraints,
            4: combination_4.add_constraints,
            5: combination_5.add_constraints,
            6: combination_6.add_constraints,
            7: combination_7.add_constraints,
            8: combination_8.add_constraints,
        }

        cfg.logger.debug(f"Adding constraints combination {self._combination} for {self.name}")

        constraint_function = constraint_functions.get(self._combination, combination_1.add_constraints)
        constraint_function(self, time, model, parameters)

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        """Add objective function terms for thermal equipment."""
        if time not in self.optimisation_time_window:
            return

        # Variable cost term: cost * power * time_step / 60
        variable_cost = self.variable_cost.get_value(time)
        power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
        model.add_objective(variable_cost * power_level_var * parameters.timestep.total_hours(), "minimize")

        if len(parameters.target_times) > 0 and time not in parameters.target_times:
            model.add_objective(-price_forecast * power_level_var * parameters.timestep.total_hours(), "minimize")

        # Startup cost term: startup_cost * turned_on
        if self.startup_cost is not None:
            startup_cost = self.startup_cost.get_value(time)
            turned_on_var = model.get_variable(f"t_on_of_{self.name}_{time}")
            model.add_objective(startup_cost * turned_on_var, "minimize")

    def get_initial_time_window(
        self, parameters: PortfolioOptimisationParameters
    ) -> tuple[list[DateTime], list[DateTime]]:
        """
        Get the list of initial condition timestamps required for this thermal unit.

        Args:
            parameters: Portfolio optimization parameters

        Returns:
            List of initial condition timestamps
        """
        self.T_traceback = max(self._T_on + self._T_start, self._T_off + self._T_stop)

        initial_times: list[DateTime] = []
        stable_initial_times: list[DateTime] = []

        if self.T_traceback > 0:
            for k in range(self.T_traceback, 0, -1):
                initial_times.append(parameters.start_date - k * parameters.timestep)
        else:
            initial_times.append(parameters.start_date - parameters.timestep)

        for k in range(self.T_traceback, 1, -1):
            stable_initial_times.append(parameters.start_date - k * parameters.timestep)

        return initial_times, stable_initial_times

    def get_optimisation_time_window(
        self, start_date: DateTime, end_date: DateTime, timestep: Duration
    ) -> list[DateTime]:
        """Get optimisation time windows based on additional hours."""

        self.optimisation_time_window = generate_datetimes(
            start=start_date, end=end_date + self.additional_hours, freq=timestep
        )
        return self.optimisation_time_window

    def add_initial_variables(
        self, model: OptimisationModel, initial_times: list[DateTime], stable_initial_times: list[DateTime]
    ):
        """
        Add initial variables for thermal unit at a specific timestamp.

        Args:
            model: Optimization model
            parameters: Portfolio optimization parameters
            initial_times: List of initial timestamps to process
            stable_initial_times: List of stable initial timestamps to process
        """

        for time in initial_times:
            # Binary state variables
            model.add_boolean_variable(f"OFF_var_{self.name}_{time}")
            model.add_boolean_variable(f"ON_UP_var_{self.name}_{time}")
            model.add_boolean_variable(f"ON_DOWN_var_{self.name}_{time}")

            # Auxiliary binary variables for transitions
            model.add_boolean_variable(f"t_on_of_{self.name}_{time}")
            model.add_boolean_variable(f"t_off_of_{self.name}_{time}")

            model.add_continuous_variable(f"{self.name}_power_level_{time}", 0.0, self.maximum_power.max())

            # Conditional state variables based on time constraints
            if self._T_start >= 1:
                model.add_boolean_variable(f"ON_START_{self.name}_{time}")

            if self._T_stop >= 1:
                model.add_boolean_variable(f"STOP_{self.name}_{time}")

            if self._T_stop >= 1 and self._T_stable >= 1:
                model.add_boolean_variable(f"flat_down_stop_{time}_{self.name}")

            if self._T_stop >= 1 and self._T_stable == 0:
                model.add_boolean_variable(f"down_to_stop_grad_{time}_{self.name}")

            if self._T_stable >= 1 and (self._T_start >= 1 or self._T_stop >= 1):
                max_power = self.maximum_power.max()
                model.add_continuous_variable(f"DD_grad_{time}_{self.name}", -max_power, max_power)

            if self._T_stable >= 1:
                # Gradient auxiliary variables for stable case
                max_power = self.maximum_power.max()
                model.add_continuous_variable(f"UP_grad_{time}_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"DOWN_grad_{time}_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"aux_up_grad_{time}_{self.name}", -max_power, max_power)
                model.add_continuous_variable(f"aux_down_grad_{time}_{self.name}", -max_power, max_power)

        if self._T_stable >= 1:
            for time in stable_initial_times:
                model.add_boolean_variable(f"ON_FLAT_{self.name}_{time}")
                model.add_boolean_variable(f"stable_{time}_{self.name}")
                model.add_boolean_variable(f"entered_up_{time}_{self.name}")
                model.add_boolean_variable(f"entered_down_{time}_{self.name}")

    def add_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        Add initial conditions for thermal unit at a specific timestamp.

        Args:
            model: Optimization model
            parameters: Portfolio optimization parameters
            time: Current timestamp to process
        """
        self._compute_time_parameters(parameters)

        initial_times, stable_initial_times = self.get_initial_time_window(parameters)

        self.add_initial_variables(model, initial_times, stable_initial_times)

        power_timeseries = (
            self.power.get_forecast(parameters.execution_date, initial_times[0], initial_times[-1])
            if self.power is not None
            else None
        )

        # Determine if this is dayZero initialization
        day_zero = power_timeseries is None
        if power_timeseries is not None:
            if parameters.start_date - parameters.timestep != power_timeseries.last_date():
                day_zero = True

        # Get initial condition function based on combination
        # Type: functions accept thermal_unit, model, parameters, extended_start_date,
        # power_timeseries, day_zero, and **kwargs (initial_times, stable_initial_times)
        initial_condition_functions: dict[int, Callable[..., None]] = {
            1: combination_1.add_initial_conditions,
            2: combination_2.add_initial_conditions,
            3: combination_3.add_initial_conditions,
            4: combination_4.add_initial_conditions,
            5: combination_5.add_initial_conditions,
            6: combination_6.add_initial_conditions,
            7: combination_7.add_initial_conditions,
            8: combination_8.add_initial_conditions,
        }

        initial_condition_function = initial_condition_functions.get(
            self._combination, combination_1.add_initial_conditions
        )

        # Call the function with single timestamp
        initial_condition_function(
            thermal_unit=self,
            model=model,
            parameters=parameters,
            extended_start_date=initial_times[0],
            day_zero=day_zero,
            power_timeseries=power_timeseries,
            initial_times=initial_times,
            stable_initial_times=stable_initial_times,
        )

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
