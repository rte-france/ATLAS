"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pendulum
from pendulum import Duration

import atlas.config as cfg
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.thermal.constraint_builder import ThermalPOConstraintBuilder
from atlas.modules.portfolio_optimisation.input_objects.thermal.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.steps.base import EquipmentPOStep
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.model_var import ModelVar
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class ThermalPOStep(EquipmentPOStep[ThermalPO]):
    """
    Step class owning all optimisation logic for ThermalPO.

    Uses __getattr__ delegation to self.equipment so that ThermalPOConstraintBuilder
    and initial_conditions_utils can access data fields transparently without changes.
    ModelVar objects are stored on the step instance and take precedence over delegation.
    """

    def __init__(self, equipment: ThermalPO):
        super().__init__(equipment)
        self._builder: ThermalPOConstraintBuilder = None  # type: ignore[assignment]

        # ModelVar placeholders — set in _setup_state_variables
        self.off_var: ModelVar = None  # type: ignore[assignment]
        self.on_flat_var: ModelVar = None  # type: ignore[assignment]
        self.on_up_var: ModelVar = None  # type: ignore[assignment]
        self.on_down_var: ModelVar = None  # type: ignore[assignment]
        self.on_start_var: ModelVar = None  # type: ignore[assignment]
        self.entered_up_var: ModelVar = None  # type: ignore[assignment]
        self.entered_down_var: ModelVar = None  # type: ignore[assignment]
        self.stable_var: ModelVar = None  # type: ignore[assignment]
        self.flat_down_stop: ModelVar = None  # type: ignore[assignment]
        self.down_to_stop_grad: ModelVar = None  # type: ignore[assignment]
        self.stop_var: ModelVar = None  # type: ignore[assignment]
        self.turned_off: ModelVar = None  # type: ignore[assignment]
        self.turned_on: ModelVar = None  # type: ignore[assignment]
        self.power_level_var: ModelVar = None  # type: ignore[assignment]
        self.up_grad_var: ModelVar = None  # type: ignore[assignment]
        self.aux_up_grad_var: ModelVar = None  # type: ignore[assignment]
        self.down_grad_var: ModelVar = None  # type: ignore[assignment]
        self.aux_down_grad_var: ModelVar = None  # type: ignore[assignment]
        self.dd_grad_var: ModelVar = None  # type: ignore[assignment]

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

            if eq._T_start >= 1:
                self.on_start_var.set_model_var(time)
            if eq._T_stop >= 1:
                self.stop_var.set_model_var(time)
            if eq._T_stable >= 1:
                self.on_flat_var.set_model_var(time)
                self.stable_var.set_model_var(time)
                self.entered_up_var.set_model_var(time)
                self.entered_down_var.set_model_var(time)
                self.up_grad_var.set_model_var(time)
                self.aux_up_grad_var.set_model_var(time)
                self.down_grad_var.set_model_var(time)
                self.aux_down_grad_var.set_model_var(time)
            if eq._T_stop >= 1 and eq._T_start == 0 and eq._T_stable == 0:
                self.down_to_stop_grad.set_model_var(time)
            if eq._T_stop >= 1 and eq._T_stable >= 1:
                self.flat_down_stop.set_model_var(time)
            if eq._T_stable >= 1 and (eq._T_start >= 1 or eq._T_stop >= 1):
                self.dd_grad_var.set_model_var(time)
            if eq._T_stop >= 1 and eq._T_start >= 1 and eq._T_stable == 0:
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
            cfg.logger.debug(f"Adding constraints combination {eq._combination} for {eq.name}")
            self._builder.add_constraints(model, time, parameters)

        self._add_daily_energy_constraint(model, parameters.temporal.timestep)

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict = {}
    ):
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

    def add_initial_conditions(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        eq._compute_time_parameters(parameters)
        self._setup_state_variables(model)
        self._add_initial_variables(parameters)

        initial_times, stable_initial_times = self._get_initial_time_window(parameters)

        power_ts = (
            eq.power.get_forecast(parameters.temporal.execution_date, initial_times[0], initial_times[-1])
            if eq.power is not None
            else None
        )

        day_zero = power_ts is None
        if power_ts is not None:
            if parameters.temporal.start_date - parameters.temporal.timestep != power_ts.last_date():
                day_zero = True

        self._builder = ThermalPOConstraintBuilder(self)
        self._builder.add_initial_conditions(
            parameters=parameters,
            extended_start_date=initial_times[0],
            day_zero=day_zero,
            power_ts=power_ts,
            initial_times=initial_times,
            stable_initial_times=stable_initial_times,
        )

    def _get_initial_time_window(self, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        eq.T_traceback = max(eq._T_on + eq._T_start, eq._T_off + eq._T_stop)

        initial_times = []
        stable_initial_times = []

        if eq.T_traceback > 0:
            for k in range(eq.T_traceback, 0, -1):
                initial_times.append(parameters.temporal.start_date - k * parameters.temporal.timestep)
        else:
            initial_times.append(parameters.temporal.start_date - parameters.temporal.timestep)

        for k in range(eq.T_traceback, 1, -1):
            stable_initial_times.append(parameters.temporal.start_date - k * parameters.temporal.timestep)

        return initial_times, stable_initial_times

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
        eq = self.equipment
        if eq._T_stable >= 1:
            self.on_up_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.on_down_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.on_flat_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.stable_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.entered_up_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
            self.entered_down_var.set_model_var(parameters.temporal.start_date - parameters.temporal.timestep)
        if eq._T_stable >= 1 and (eq._T_start >= 1 or eq._T_stop >= 1):
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
