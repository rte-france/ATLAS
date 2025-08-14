"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.wind import Wind
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated, get_variable_cost
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel


class WindPO(Wind):
    maximum_fcr: float
    maximum_afrr: float
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    maximum_curtailment_ratio: Timeseries | LazyTimeseries
    # variable_cost: Timeseries | LazyTimeseries

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """Build variables for solar and wind equipment."""
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding variables for wind unit {self.name} at time {time}")
            max_power = self.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)
            min_power = (1 - self.maximum_curtailment_ratio.get_value(time)) * max_power
            maximum_automated = get_maximum_automated(self)

            model.add_continuous_variable(
                name=f"{self.name}_power_level_{time}",
                lower_bound=min_power,
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
        time: DateTime,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function formulates the wind equipments constraints.
        """
        pass

    def add_objective(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding objective for wind unit {self.name} at time {time}")
            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            model.add_objective(
                get_variable_cost(self, time) * power_level_var * parameters.timestep.total_hours(),
                direction="minimize",
            )
        else:
            cfg.logger.debug(f"Skipping objective for wind unit {self.name} at non-target time {time}")
