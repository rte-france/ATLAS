"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.enums import LoadType
from atlas.modules.portfolio_optimisation.input_objects.load import LoadPO
from atlas.modules.portfolio_optimisation.steps.base import EquipmentPOStep
from atlas.modules.portfolio_optimisation.utils.getters import get_variable_cost
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class LoadPOStep(EquipmentPOStep[LoadPO]):
    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding variables for load unit {eq.name} at time {time}")
            max_power = (
                eq._cached_forecast.get_value(time) if eq._cached_forecast and time in eq._cached_forecast else 0
            )
            model.add_continuous_variable(f"{eq.name}_power_level_{time}", lower_bound=max_power, upper_bound=0)

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints for load unit {eq.name} at time {time}")
            max_power = (
                eq._cached_forecast.get_value(time) if eq._cached_forecast and time in eq._cached_forecast else 0
            )
            power_level_var = model.get_variable(f"{eq.name}_power_level_{time}")
            model.add_constraint(power_level_var >= max_power, f"power_max_{time}_{eq.name}")
            model.add_constraint(power_level_var <= 0, f"power_min_{time}_{eq.name}")

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict = {}
    ):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for load unit {eq.name} at time {time}")
            price_forecast = price_forecasts.get(time, 0.0)
            power_level_var = model.get_variable(f"{eq.name}_power_level_{time}")
            if eq.load_type == LoadType.POWER_TO_GAS:
                model.add_objective(
                    (get_variable_cost(eq, time) - price_forecast)
                    * power_level_var
                    * parameters.temporal.timestep.total_hours()
                )
            else:
                model.add_objective(
                    get_variable_cost(eq, time) * -power_level_var * parameters.temporal.timestep.total_hours()
                )
