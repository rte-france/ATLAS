"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime, Duration

import atlas.config as cfg
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated, get_variable_cost
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes


class WindPO(Wind):
    maximum_fcr: float
    maximum_afrr: float
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    maximum_curtailment_ratio: Timeseries | LazyTimeseries

    optimisation_time_window: list[DateTime] = []
    _cached_forecast: Timeseries | None = None

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """
        Build variables for solar and wind equipment.

        :param model: Optimization model
        :type model: OptimisationModel
        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """
        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding variables for wind unit {self.name} at time {time}")
            max_power = self._cached_forecast.get_value(time) if self._cached_forecast else 0
            min_power = (1 - self.maximum_curtailment_ratio.get_value(time)) * max_power
            maximum_automated = get_maximum_automated(self)

            model.add_continuous_variable(
                name=f"{self.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

            add_reserve_variables(
                model,
                self.name,
                time,
                min_power,
                max_power,
                maximum_automated,
                relaxed_reserves=False,
                storage_equipment=False,
                thermal_equipment=False,
            )
        else:
            cfg.logger.debug(f"Skipping variables for wind unit {self.name} at non-target time {time}")

    def add_constraints(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        Formulate the wind equipment constraints.

        :param model: Optimization model
        :type model: OptimisationModel
        :param time: Current time period
        :type time: DateTime
        :param parameters: Optimization parameters
        :type parameters: PortfolioOptimisationParameters
        """

        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints for wind unit {self.name} at time {time}")

            max_power = self._cached_forecast.get_value(time) if self._cached_forecast else 0
            min_power = (1 - self.maximum_curtailment_ratio.get_value(time)) * max_power
            maximum_automated = get_maximum_automated(self)

            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")

            model.add_constraint(power_level_var <= max_power, f"power_max_{time}_{self.name}")
            model.add_constraint(power_level_var >= min_power, f"power_min_{time}_{self.name}")
            model.add_constraint(
                automated_reserves_up_var <= maximum_automated, f"automated_reserves_up_max_{time}_{self.name}"
            )
            model.add_constraint(
                automated_reserves_down_var <= maximum_automated, f"automated_reserves_down_max_{time}_{self.name}"
            )
            model.add_constraint(reserves_up_var <= max_power, f"reserves_up_max_{time}_{self.name}")
            model.add_constraint(reserves_down_var <= max_power, f"reserves_down_max_{time}_{self.name}")
        else:
            cfg.logger.debug(f"Skipping constraints for wind unit {self.name} at non-target time {time}")

    def add_objective(
        self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters, **kwargs
    ):
        if time in self.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for wind unit {self.name} at time {time}")
            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            model.add_objective(
                get_variable_cost(self, time) * power_level_var * parameters.timestep.total_hours(),
            )
        else:
            cfg.logger.debug(f"Skipping objective for wind unit {self.name} at non-target time {time}")

    def get_optimisation_time_window(
        self, start_date: DateTime, end_date: DateTime, timestep: Duration
    ) -> list[DateTime]:
        """Get optimisation time windows based on additional hours."""

        self.optimisation_time_window = generate_datetimes(
            start=start_date, end=end_date + self.additional_hours, freq=timestep
        )
        return self.optimisation_time_window

    def prefetch_forecasts(self, execution_date: DateTime):
        """Pre-fetch and cache forecasts for the entire optimization time window."""
        if not self.optimisation_time_window:
            return

        start_time = self.optimisation_time_window[0]
        end_time = self.optimisation_time_window[-1]

        self._cached_forecast = self.maximum_power_forecast.get_forecast(execution_date, start_time, end_time)
