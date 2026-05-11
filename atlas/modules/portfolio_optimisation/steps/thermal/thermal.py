"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pendulum
from pendulum import Duration

import atlas.config as cfg
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.steps.base import AbstractOptimStep
from atlas.modules.portfolio_optimisation.steps.thermal.constraint_builder import ThermalConstraintBuilder
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.model_var import ModelVar
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class ThermalStep(AbstractOptimStep[ThermalPO]):
    """
    Step class owning all optimisation logic for ThermalPO.

    Uses __getattr__ delegation to self.equipment so that ThermalConstraintBuilder
    and initial_conditions_utils can access data fields transparently without changes.
    ModelVar objects are stored on the step instance and take precedence over delegation.
    """

    def __init__(self, equipment: ThermalPO):
        super().__init__(equipment)
        self._builder: ThermalConstraintBuilder = None  # type: ignore[assignment]

        # Computed time parameters — set in _compute_time_parameters

    def __getattr__(self, name: str):
        """Delegate unknown attribute access to equipment so constraint_builder works transparently."""
        return getattr(self.equipment, name)

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        self.add_initial_conditions(model, parameters)

        eq = self.equipment
        for time in eq.optimisation_time_window:
            self.off_var.set_model_var(time)
            self.on_up_var.set_model_var(time)
            self.on_down_var.set_model_var(time)
            self.turned_on.set_model_var(time)
            self.turned_off.set_model_var(time)

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

            if eq.minimum_power is None:
                eq.minimum_power = Timeseries.from_index(
                    start_date=eq.optimisation_time_window[0],
                    end_date=eq.optimisation_time_window[-1],
                    frequency=parameters.temporal.timestep,
                    default_value=0,
                )
            minimum_power = eq.minimum_power.get_value(time)
            maximum_power = eq.maximum_power.get_value(time)
            maximum_automated = get_maximum_automated(eq)

            self.power_level_var.set_model_var(time)

            add_reserve_variables(
                model=model,
                name=eq.name,
                time=time,
                min_power=minimum_power,
                max_power=maximum_power,
                maximum_automated=maximum_automated,
                relaxed_reserves=True,
                storage_equipment=False,
                thermal_equipment=True,
            )

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints combination {self._combination} for {eq.name}")
            self._builder.add_constraints(model, time, parameters)

        self._add_daily_energy_constraint(model, parameters.temporal.timestep)

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict | None = None
    ):
        if price_forecasts is None:
            price_forecasts = {}
        eq = self.equipment
        for time in eq.optimisation_time_window:
            price_forecast = price_forecasts.get(time, 0.0)
            variable_cost = eq.variable_cost.get_value(time)
            power_level_var = self.power_level_var.get_value(time)
            model.add_objective(variable_cost * power_level_var * parameters.temporal.timestep.total_hours())

            if time > max(parameters.target_times):
                model.add_objective(-price_forecast * power_level_var * parameters.temporal.timestep.total_hours())

            if eq.startup_cost is not None:
                startup_cost = eq.startup_cost.get_value(time)
                turned_on_var = model.get_variable(f"t_on_{eq.name}_{time}")
                model.add_objective(startup_cost * turned_on_var)

    def _compute_time_parameters(self, parameters: PortfolioOptimisationParameters) -> None:
        eq = self.equipment
        self._T_on = (
            int(max(1, math.ceil(eq.minimum_time_on / parameters.temporal.timestep))) + 1
            if eq.minimum_time_on and eq.minimum_time_on.total_minutes() > 0
            else 0
        )
        self._T_off = (
            int(max(1, math.ceil(eq.minimum_time_off / parameters.temporal.timestep))) + 1
            if eq.minimum_time_off and eq.minimum_time_off.total_minutes() > 0
            else 0
        )
        self._T_start = (
            int(math.floor(eq.startup_duration / parameters.temporal.timestep)) if eq.startup_duration else 0
        )
        self._T_stop = (
            int(math.floor(eq.shutdown_duration / parameters.temporal.timestep)) if eq.shutdown_duration else 0
        )
        if eq.minimum_stable_power_duration:
            if eq.minimum_stable_power_duration < parameters.temporal.timestep:
                self._T_stable = 0
            else:
                t = int(math.ceil(eq.minimum_stable_power_duration / parameters.temporal.timestep)) + 1
                self._T_stable = t if t >= 2 else 0
        else:
            self._T_stable = 0
        self._Delta_Q = eq.maximum_gradient * parameters.temporal.timestep.total_minutes()
        self._Delta_Q_unconstrained = eq.maximum_power.slice(
            parameters.temporal.start_date, parameters.temporal.end_date, inplace=False
        ).max()
        self._combination = self._determine_combination()

    def _determine_combination(self) -> int:
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
            return 1

    def add_initial_conditions(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        self._compute_time_parameters(parameters)
        self._setup_state_variables(model)
        self._add_initial_variables(parameters)

        self._builder = ThermalConstraintBuilder(self)  # type: ignore[arg-type]
        self._builder.add_initial_conditions(parameters)

    def _setup_state_variables(self, model: OptimisationModel):
        eq = self.equipment
        self.off_var = ModelVar(
            getter=lambda time: model.get_variable(f"off_{eq.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"off_{eq.name}_{time}"),
        )
        self.on_flat_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_flat_{eq.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_flat_{eq.name}_{time}"),
        )
        self.on_up_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_up_{eq.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_up_{eq.name}_{time}"),
        )
        self.on_down_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_down_{eq.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_down_{eq.name}_{time}"),
        )
        self.on_start_var = ModelVar(
            getter=lambda time: model.get_variable(f"on_start_{eq.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"on_start_{eq.name}_{time}"),
        )
        self.entered_up_var = ModelVar(
            getter=lambda time: model.get_variable(f"entered_up_{time}_{eq.name}"),
            setter=lambda time: model.add_boolean_variable(f"entered_up_{time}_{eq.name}"),
        )
        self.entered_down_var = ModelVar(
            getter=lambda time: model.get_variable(f"entered_down_{time}_{eq.name}"),
            setter=lambda time: model.add_boolean_variable(f"entered_down_{time}_{eq.name}"),
        )
        self.stable_var = ModelVar(
            getter=lambda time: model.get_variable(f"stable_{time}_{eq.name}"),
            setter=lambda time: model.add_boolean_variable(f"stable_{time}_{eq.name}"),
        )
        self.flat_down_stop = ModelVar(
            getter=lambda time: model.get_variable(f"flat_down_stop_{time}_{eq.name}"),
            setter=lambda time: model.add_boolean_variable(f"flat_down_stop_{time}_{eq.name}"),
        )
        self.down_to_stop_grad = ModelVar(
            getter=lambda time: model.get_variable(f"down_to_stop_grad_{time}_{eq.name}"),
            setter=lambda time: model.add_boolean_variable(f"down_to_stop_grad_{time}_{eq.name}"),
        )
        self.stop_var = ModelVar(
            getter=lambda time: model.get_variable(f"stop_{eq.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"stop_{eq.name}_{time}"),
        )
        self.turned_off = ModelVar(
            getter=lambda time: model.get_variable(f"t_off_{eq.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"t_off_{eq.name}_{time}"),
        )
        self.turned_on = ModelVar(
            getter=lambda time: model.get_variable(f"t_on_{eq.name}_{time}"),
            setter=lambda time: model.add_boolean_variable(f"t_on_{eq.name}_{time}"),
        )
        self.power_level_var = ModelVar(
            getter=lambda time: model.get_variable(f"{eq.name}_power_level_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{eq.name}_power_level_{time}", 0, eq.maximum_power.get_value(time)
            ),
        )
        self.up_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"up_grad_{time}_{eq.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"up_grad_{time}_{eq.name}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )
        self.down_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"down_grad_{time}_{eq.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"down_grad_{time}_{eq.name}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )
        self.aux_up_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"aux_up_grad_{time}_{eq.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"aux_up_grad_{time}_{eq.name}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )
        self.aux_down_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"aux_down_grad_{time}_{eq.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"aux_down_grad_{time}_{eq.name}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )
        self.dd_grad_var = ModelVar(
            getter=lambda time: model.get_variable(f"dd_grad_{time}_{eq.name}"),
            setter=lambda time: model.add_continuous_variable(
                f"dd_grad_{time}_{eq.name}", -eq.maximum_power.get_value(time), eq.maximum_power.get_value(time)
            ),
        )

    def _add_initial_variables(self, parameters: PortfolioOptimisationParameters):
        if self._T_stable >= 1:
            self.on_up_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.on_down_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.on_flat_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.stable_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.entered_up_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.entered_down_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
        if self._T_stable >= 1 and (self._T_start >= 1 or self._T_stop >= 1):
            self.dd_grad_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)

    def _add_daily_energy_constraint(self, model: OptimisationModel, timestep: Duration):
        eq = self.equipment
        if eq.has_daily_energy_constraint:
            days_in_optimes = sorted({pendulum.datetime(t.year, t.month, t.day) for t in eq.optimisation_time_window})
            for idx, date in enumerate(days_in_optimes):
                matching_steps = [
                    t
                    for t in eq.optimisation_time_window
                    if (t.year == date.year and t.month == date.month and t.day == date.day)
                ]
                if matching_steps and eq.maximum_daily_energy is not None:
                    constraint_expr = sum(
                        self.power_level_var.get_value(t) for t in matching_steps
                    ) <= eq.maximum_daily_energy.get_value(date) * timestep.total_days() * len(matching_steps)
                    model.add_constraint(constraint_expr, f"energy_limit_day_{idx}_{eq.name}")
