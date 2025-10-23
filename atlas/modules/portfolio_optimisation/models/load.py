"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime

import atlas.config as cfg
from atlas.enum import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.load import Load
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_variable_cost
from atlas.solver.solver_interface import OptimisationModel


class LoadPO(Load):
    load_type: LoadType
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """Build variables for load equipment."""
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding variables for load unit {self.name} at time {time}")
            max_power = self.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)

            model.add_continuous_variable(
                f"{self.name}_power_level_{time}",
                lower_bound=max_power,
                upper_bound=0,
            )
        else:
            cfg.logger.debug(f"Skipping variables for load unit {self.name} at non-target time {time}")

    def add_constraints(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """
        This function adds constraints related to load equipments.
        """
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding constraints for load unit {self.name} at time {time}")
            max_power = self.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)
            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")

            model.add_constraint(power_level_var >= max_power)
            model.add_constraint(power_level_var <= 0)
        else:
            cfg.logger.debug(f"Skipping constraints for load unit {self.name} at non-target time {time}")

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding objective for load unit {self.name} at time {time}")
            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            if self.load_type == LoadType.POWER_TO_GAS:
                model.add_objective(
                    (get_variable_cost(self, time) - price_forecast) * power_level_var * parameters.timestep,
                    direction="minimize",
                )
            else:
                model.add_objective(
                    get_variable_cost(self, time) * -power_level_var * parameters.timestep, direction="minimize"
                )
        else:
            cfg.logger.debug(f"Skipping objective for load unit {self.name} at non-target time {time}")
