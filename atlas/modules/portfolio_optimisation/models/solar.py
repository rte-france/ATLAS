"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime, Duration

import atlas.config as cfg
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.solar import Solar
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated, get_variable_cost
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel
from atlas.timing import generate_datetimes


class SolarPO(Solar):
    maximum_fcr: float
    maximum_afrr: float
    maximum_curtailment_ratio: Timeseries | LazyTimeseries
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    # variable_cost: Timeseries | LazyTimeseries

    def add_variables(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        """Build variables for solar and wind equipment."""
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding variables for solar unit {self.name} at time {time}")
            max_power = self.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)
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
            cfg.logger.debug(f"Skipping variables for solar unit {self.name} at non-target time {time}")

    def add_constraints(
        self,
        model: OptimisationModel,
        time: DateTime,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function formulates the photovoltaic equipments constraints.
        """
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding constraints for solar unit {self.name} at time {time}")
            max_power = self.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)
            min_power = (1 - self.maximum_curtailment_ratio.get_value(time)) * max_power
            maximum_automated = get_maximum_automated(self)

            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{self.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{self.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_{self.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_{self.name}_{time}")

            model.add_constraint(power_level_var <= max_power)
            model.add_constraint(power_level_var >= min_power)
            model.add_constraint(automated_reserves_up_var <= maximum_automated)
            model.add_constraint(automated_reserves_down_var <= maximum_automated)
            model.add_constraint(reserves_up_var <= max_power)
            model.add_constraint(reserves_down_var <= max_power)
        else:
            cfg.logger.debug(f"Skipping constraints for solar unit {self.name} at non-target time {time}")

    def add_objective(
        self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters, **kwargs
    ):
        if time in parameters.target_times:
            cfg.logger.debug(f"Adding objective for solar unit {self.name} at time {time}")
            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            model.add_objective(
                get_variable_cost(self, time) * power_level_var * parameters.timestep.total_hours(),
                direction="minimize",
            )
        else:
            cfg.logger.debug(f"Skipping objective for solar unit {self.name} at non-target time {time}")

    def get_optimisation_time_window(
        self, start_date: DateTime, end_date: DateTime, timestep: Duration
    ) -> list[DateTime]:
        """Get optimisation time windows based on additional hours."""
        return generate_datetimes(start=start_date, end=end_date + self.additional_hours, freq=timestep)
