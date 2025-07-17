"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pendulum import DateTime

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.solar import Solar
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated, get_variable_cost
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel


class SolarPO(Solar):
    maximum_fcr: float
    maximum_afrr: float
    maximum_curtailment_ratio: Timeseries | LazyTimeseries
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    variable_cost: Timeseries | LazyTimeseries

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """Build variables for solar and wind equipment."""
        for time in parameters.target_times:
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

    def add_constraints(
        self,
        time: DateTime,
        model: OptimisationModel,
        parameters: PortfolioOptimisationParameters,
    ):
        """
        This function formulates the photovoltaic equipments constraints.
        """

        if time in parameters.op_times:
            max_power = self.maximum_power_forecast.get_forecast(parameters.execution_date, time, time).get_value(time)
            min_power = (1 - self.maximum_curtailment_ratio.get_value(time)) * max_power
            maximum_automated = get_maximum_automated(self)

            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            automated_reserves_up_var = model.get_variable(f"automated_res_up_e_{self.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_res_down_e_{self.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_e_{self.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_e_{self.name}_{time}")

            model.add_constraint(power_level_var <= max_power)
            model.add_constraint(power_level_var >= min_power)
            model.add_constraint(automated_reserves_up_var <= maximum_automated)
            model.add_constraint(automated_reserves_down_var <= maximum_automated)
            model.add_constraint(reserves_up_var <= max_power)
            model.add_constraint(reserves_down_var <= max_power)

    def add_objective(self, model: OptimisationModel, time: DateTime, parameters: PortfolioOptimisationParameters):
        if time in parameters.target_times:
            power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
            model.add_objective(get_variable_cost(self, time) * power_level_var * parameters.timestep)
