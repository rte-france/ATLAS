"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime, Duration

import atlas.config as cfg
from atlas.enums import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.base_equipment import BaseEquipmentPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_variable_cost
from atlas.objects.equipment.load import Load
from atlas.solver.solver_interface import OptimisationModel


class LoadPO(BaseEquipmentPO, Load):
    load_type: LoadType
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    additional_hours: Duration

    optimisation_time_window: list[DateTime] = []
    _cached_forecast: Timeseries | None = None

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """
        Build variables for load equipment.

        :param model: Optimization model
        :type model: OptimisationModel
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """
        for time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding variables for load unit {self.name} at time {time}")
            max_power = (
                self._cached_forecast.get_value(time) if self._cached_forecast and time in self._cached_forecast else 0
            )

            model.add_continuous_variable(
                f"{self.name}_power_level_{time}",
                lower_bound=max_power,
                upper_bound=0,
            )

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """
        This function adds constraints related to load equipments.
        """
        for time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints for load unit {self.name} at time {time}")
            max_power = (
                self._cached_forecast.get_value(time) if self._cached_forecast and time in self._cached_forecast else 0
            )
            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")

            model.add_constraint(power_level_var >= max_power, f"power_max_{time}_{self.name}")
            model.add_constraint(power_level_var <= 0, f"power_min_{time}_{self.name}")

    def add_objective(
        self,
        model: OptimisationModel,
        time: DateTime,
        price_forecast: float,
        parameters: PortfolioOptimisationParameters,
    ):
        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for load unit {self.name} at time {time}")
            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            if self.load_type == LoadType.POWER_TO_GAS:
                model.add_objective(
                    (get_variable_cost(self, time) - price_forecast)
                    * power_level_var
                    * parameters.temporal.timestep.total_hours(),
                )
            else:
                model.add_objective(
                    get_variable_cost(self, time) * -power_level_var * parameters.temporal.timestep.total_hours(),
                )
        else:
            cfg.logger.debug(f"Skipping objective for load unit {self.name} at non-target time {time}")

    def prefetch_forecasts(self, execution_date: DateTime):
        """
        Pre-fetch and cache forecasts for the entire optimization time window.

        :param execution_date: Execution date for the forecast
        :type execution_date: DateTime
        """
        if not self.optimisation_time_window:
            return

        start_time = self.optimisation_time_window[0]
        end_time = self.optimisation_time_window[-1]

        self._cached_forecast = self.maximum_power_forecast.get_forecast(execution_date, start_time, end_time)
