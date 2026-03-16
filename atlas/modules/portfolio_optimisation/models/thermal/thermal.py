"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pendulum
from pendulum import DateTime, Duration
from pydantic import model_validator

import atlas.config as cfg
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.thermal import Thermal
from atlas.modules.portfolio_optimisation.models.base_equipment import BaseEquipmentPO
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
from atlas.solver.model_var import ModelVar
from atlas.solver.solver_interface import OptimisationModel


class ThermalPO(BaseEquipmentPO, Thermal):
    """
    Sophisticated unit commitment model for thermal power equipment.

    This implements a state-of-the-art thermal unit optimization with multiple
    operational states, complex time constraints, and ramping limitations.
    """

    maximum_fcr: float
    maximum_afrr: float
    maximum_power: AbstractTimeseries
    variable_cost: AbstractTimeseries
    maximum_gradient: float = 0.0
    has_daily_energy_constraint: bool = False

    _T_on: int = 0
    _T_off: int = 0
    _T_start: int = 0
    _T_stop: int = 0
    _T_stable: int = 0
    _Delta_Q: float = 0.0
    _Delta_Q_unconstrained: float = 0.0
    _combination: int = 1
    T_traceback: int = 0
    optimisation_time_window: list[DateTime] = []

    off_var: ModelVar = None  # type:ignore [assignment]
    on_flat_var: ModelVar = None  # type:ignore [assignment]
    on_up_var: ModelVar = None  # type:ignore [assignment]
    on_down_var: ModelVar = None  # type:ignore [assignment]
    on_start_var: ModelVar = None  # type:ignore [assignment]
    entered_up_var: ModelVar = None  # type:ignore [assignment]
    entered_down_var: ModelVar = None  # type:ignore [assignment]
    stable_var: ModelVar = None  # type:ignore [assignment]
    flat_down_stop: ModelVar = None  # type:ignore [assignment]
    down_to_stop_grad: ModelVar = None  # type:ignore [assignment]
    stop_var: ModelVar = None  # type:ignore [assignment]
    turned_off: ModelVar = None  # type:ignore [assignment]
    turned_on: ModelVar = None  # type:ignore [assignment]
    power_level_var: ModelVar = None  # type:ignore [assignment]
    up_grad_var: ModelVar = None  # type:ignore [assignment]
    aux_up_grad_var: ModelVar = None  # type:ignore [assignment]
    down_grad_var: ModelVar = None  # type:ignore [assignment]
    aux_down_grad_var: ModelVar = None  # type:ignore [assignment]
    dd_grad_var: ModelVar = None  # type:ignore [assignment]

    def _compute_time_parameters(self, parameters: PortfolioOptimisationParameters):
        """
        Compute time step parameters from duration constraints.

        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """

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
                self._T_stable = self._T_stable if self._T_stable >= 2 else 0
        else:
            self._T_stable = 0

        self._Delta_Q = self.maximum_gradient * parameters.timestep.total_minutes()
        self._Delta_Q_unconstrained = self.maximum_power.slice(
            parameters.date.start_date, parameters.date.end_date, inplace=False
        ).max()

        self._combination = self._determine_combination()

    def _determine_combination(self) -> int:
        """
        Determine which of the 8 constraint combinations to use.

        :return: Combination number (1-8)
        :rtype: int
        """
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
            cfg.logger("Combination constraint set can not be determined, default to 1.")
            return 1  # Default fallback

    def add_variables(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        Build variables for complex thermal unit commitment.

        :param model: Optimization model
        :type model: OptimisationModel
        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """

        # Always defined state variables for optimization time frame
        if time in self.optimisation_time_window:
            # Binary state variables
            self.off_var.set_model_var(time)
            self.on_up_var.set_model_var(time)
            self.on_down_var.set_model_var(time)

            # Auxiliary binary variables for transitions
            self.turned_on.set_model_var(time)
            self.turned_off.set_model_var(time)

            # Conditional state variables based on time constraints
            if self._T_start >= 1:
                self.on_start_var.set_model_var(time)

            if self._T_stop >= 1:
                self.stop_var.set_model_var(time)

            if self._T_stable >= 1:
                self.on_flat_var.set_model_var(time)
                self.stable_var.set_model_var(time)
                self.entered_up_var.set_model_var(time)
                self.entered_down_var.set_model_var(time)

                self.up_grad_var.set_model_var(time)
                self.aux_up_grad_var.set_model_var(time)
                self.down_grad_var.set_model_var(time)
                self.aux_down_grad_var.set_model_var(time)

            if self._T_stop >= 1 and self._T_start == 0 and self._T_stable == 0:
                self.down_to_stop_grad.set_model_var(time)

            if self._T_stop >= 1 and self._T_stable >= 1:
                self.flat_down_stop.set_model_var(time)

            if self._T_stable >= 1 and (self._T_start >= 1 or self._T_stop >= 1):
                self.dd_grad_var.set_model_var(time)

            if self._T_stop >= 1 and self._T_start >= 1 and self._T_stable == 0:
                self.down_to_stop_grad.set_model_var(time)

            if self.minimum_power is None:
                self.minimum_power = Timeseries.from_index(
                    start_date=self.optimisation_time_window[0],
                    end_date=self.optimisation_time_window[-1],
                    frequency=parameters.timestep,
                    default_value=0,
                )
            minimum_power = self.minimum_power.get_value(time)
            maximum_power = self.maximum_power.get_value(time)
            maximum_automated = get_maximum_automated(self)

            self.power_level_var.set_model_var(time)

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
        """
        Add constraints based on the determined combination.

        :param model: Optimization model
        :type model: OptimisationModel
        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """
        if time in self.optimisation_time_window:
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
        """
        Add objective function terms for thermal equipment.

        :param model: Optimization model
        :type model: OptimisationModel
        :param time: Current time period
        :type time: DateTime
        :param price_forecast: Forecasted price
        :type price_forecast: float
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """
        if time in self.optimisation_time_window:
            variable_cost = self.variable_cost.get_value(time)
            power_level_var = self.power_level_var.get_value(time)
            model.add_objective(
                variable_cost * power_level_var * parameters.timestep.total_hours(),
            )

            if time > max(parameters.target_times):
                model.add_objective(
                    -price_forecast * power_level_var * parameters.timestep.total_hours(),
                )

            if self.startup_cost is not None:
                startup_cost = self.startup_cost.get_value(time)
                turned_on_var = model.get_variable(f"t_on_{self.name}_{time}")
                model.add_objective(startup_cost * turned_on_var)

    def _get_initial_time_window(
        self, parameters: PortfolioOptimisationParameters
    ) -> tuple[list[DateTime], list[DateTime]]:
        """
        Get the list of initial condition timestamps required for this thermal unit.
        """
        self.T_traceback = max(self._T_on + self._T_start, self._T_off + self._T_stop)

        initial_times: list[DateTime] = []
        stable_initial_times: list[DateTime] = []

        if self.T_traceback > 0:
            for k in range(self.T_traceback, 0, -1):
                initial_times.append(parameters.date.start_date - k * parameters.timestep)
        else:
            initial_times.append(parameters.date.start_date - parameters.timestep)

        for k in range(self.T_traceback, 1, -1):
            stable_initial_times.append(parameters.date.start_date - k * parameters.timestep)

        return initial_times, stable_initial_times

    def _setup_state_variables(self, model: OptimisationModel):
        self.off_var = ModelVar(
            getter=lambda time: model.get_variable(f"off_{self.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"off_{self.name}_{time}"),
        )
        self.on_flat_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_flat_{self.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_flat_{self.name}_{time}"),
        )
        self.on_up_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_up_{self.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_up_{self.name}_{time}"),
        )
        self.on_down_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_down_{self.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_down_{self.name}_{time}"),
        )
        self.on_start_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_start_{self.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_start_{self.name}_{time}"),
        )
        self.entered_up_var = ModelVar(
            getter=lambda time: model.get_variable(f"entered_up_{time}_{self.name}"),
            setter=lambda time: model.add_boolean_variable(f"entered_up_{time}_{self.name}"),
        )
        self.entered_down_var = ModelVar(
            getter=lambda time: model.get_variable(f"entered_down_{time}_{self.name}"),
            setter=lambda time: model.add_boolean_variable(f"entered_down_{time}_{self.name}"),
        )
        self.stable_var = ModelVar(
            getter=lambda time: model.get_variable(f"stable_{time}_{self.name}"),
            setter=lambda time: model.add_boolean_variable(f"stable_{time}_{self.name}"),
        )
        self.flat_down_stop = ModelVar(
            getter=lambda time: model.get_variable(f"flat_down_stop_{time}_{self.name}"),
            setter=lambda time: model.add_boolean_variable(f"flat_down_stop_{time}_{self.name}"),
        )
        self.down_to_stop_grad = ModelVar(
            getter=lambda time: model.get_variable(f"down_to_stop_grad_{time}_{self.name}"),
            setter=lambda time: model.add_boolean_variable(f"down_to_stop_grad_{time}_{self.name}"),
        )
        self.stop_var = ModelVar(
            getter=lambda time: model.get_variable(f"stop_{self.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"stop_{self.name}_{time}"),
        )
        self.turned_off = ModelVar(
            getter=lambda time: model.get_variable(f"t_off_{self.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"t_off_{self.name}_{time}"),
        )
        self.turned_on = ModelVar(
            getter=lambda time: model.get_variable(f"t_on_{self.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"t_on_{self.name}_{time}"),
        )
        self.power_level_var = ModelVar(
            getter=lambda time: model.get_variable(f"{self.name}_power_level_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{self.name}_power_level_{time}", 0, self.maximum_power.get_value(time)
            ),
        )
        self.up_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"up_grad_{time}_{self.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"up_grad_{time}_{self.name}",
                -self.maximum_power.get_value(time),
                self.maximum_power.get_value(time),
            ),
        )
        self.down_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"down_grad_{time}_{self.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"down_grad_{time}_{self.name}",
                -self.maximum_power.get_value(time),
                self.maximum_power.get_value(time),
            ),
        )
        self.aux_up_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"aux_up_grad_{time}_{self.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"aux_up_grad_{time}_{self.name}",
                -self.maximum_power.get_value(time),
                self.maximum_power.get_value(time),
            ),
        )
        self.aux_down_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"aux_down_grad_{time}_{self.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"aux_down_grad_{time}_{self.name}",
                -self.maximum_power.get_value(time),
                self.maximum_power.get_value(time),
            ),
        )
        self.dd_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"dd_grad_{time}_{self.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"dd_grad_{time}_{self.name}",
                -self.maximum_power.get_value(time),
                self.maximum_power.get_value(time),
            ),
        )

    def _add_initial_variables(self, parameters: PortfolioOptimisationParameters):
        """Add initial variables for timestep not included in optimisation times"""
        if self._T_stable >= 1:
            self.on_up_var.set_model_var(parameters.date.start_date - parameters.timestep)
            self.on_down_var.set_model_var(parameters.date.start_date - parameters.timestep)
            self.on_flat_var.set_model_var(parameters.date.start_date - parameters.timestep)
            self.stable_var.set_model_var(parameters.date.start_date - parameters.timestep)
            self.entered_up_var.set_model_var(parameters.date.start_date - parameters.timestep)
            self.entered_down_var.set_model_var(parameters.date.start_date - parameters.timestep)

        if self._T_stable >= 1 and (self._T_start >= 1 or self._T_stop >= 1):
            self.dd_grad_var.set_model_var(parameters.date.start_date - parameters.timestep)

    def add_initial_conditions(
        self,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        Add initial conditions for thermal unit at a specific timestamp.
        """
        self._compute_time_parameters(parameters)
        self._setup_state_variables(model)
        self._add_initial_variables(parameters)

        initial_times, stable_initial_times = self._get_initial_time_window(parameters)

        power_ts = (
            self.power.get_forecast(parameters.date.execution_date, initial_times[0], initial_times[-1])
            if self.power is not None
            else None
        )

        # Determine if this is dayZero initialization
        day_zero = power_ts is None
        if power_ts is not None:
            if parameters.date.start_date - parameters.timestep != power_ts.last_date():
                day_zero = True

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
            obj=self,
            parameters=parameters,
            extended_start_date=initial_times[0],
            day_zero=day_zero,
            power_ts=power_ts,
            initial_times=initial_times,
            stable_initial_times=stable_initial_times,
        )

    def add_daily_energy_constraint(self, model: OptimisationModel, timestep: Duration):
        if self.has_daily_energy_constraint:
            days_in_optimes = sorted({pendulum.datetime(t.year, t.month, t.day) for t in self.optimisation_time_window})

            for idx, date in enumerate(days_in_optimes):
                matching_steps = [
                    t
                    for t in self.optimisation_time_window
                    if (t.year == date.year and t.month == date.month and t.day == date.day)
                ]

                if matching_steps and self.maximum_daily_energy is not None:
                    constraint_expr = sum(
                        self.power_level_var.get_value(t) for t in matching_steps
                    ) <= self.maximum_daily_energy.get_value(date) * timestep.total_days() * len(matching_steps)
                    model.add_constraint(constraint_expr, f"energy_limit_day_{idx}_{self.name}")

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
