"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime

from atlas.enum import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.load import Load
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_variable_cost
from atlas.solver.solver_interface import OptimisationModel


class LoadPO(Load):
    load_type: LoadType
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    variable_cost: Timeseries | LazyTimeseries

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """Build variables for load equipment."""

        for time in parameters.target_times:
            max_power = self.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)

            model.add_continuous_variable(
                f"{self.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

    def add_constraints(self, time: DateTime, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """
        This function adds constraints related to load equipments.
        """
        max_power = self.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)
        power_level_var = model.get_variable(f"{self.name}_power_level_{time}")

        model.add_constraint(power_level_var >= max_power)
        model.add_constraint(power_level_var <= 0)

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        if time in parameters.target_times:
            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            if self.load_type == LoadType.POWER_TO_GAS:
                model.add_objective(
                    (get_variable_cost(self, time) - price_forecast) * power_level_var * parameters.timestep
                )
            else:
                model.add_objective(get_variable_cost(self, time) * -power_level_var * parameters.timestep)
