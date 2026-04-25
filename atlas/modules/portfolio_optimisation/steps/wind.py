"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.modules.portfolio_optimisation.input_objects.wind import WindPO
from atlas.modules.portfolio_optimisation.steps.base import EquipmentPOStep
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_automated, get_variable_cost
from atlas.modules.portfolio_optimisation.utils.variable_utils import add_reserve_variables
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class WindPOStep(EquipmentPOStep[WindPO]):
    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding variables for wind unit {eq.name} at time {time}")
            max_power = eq._cached_forecast.get_value(time) if eq._cached_forecast else 0
            min_power = (1 - eq.maximum_curtailment_ratio.get_value(time)) * max_power
            maximum_automated = get_maximum_automated(eq)

            model.add_continuous_variable(name=f"{eq.name}_power_level_{time}", lower_bound=0, upper_bound=max_power)
            add_reserve_variables(
                model,
                eq.name,
                time,
                min_power,
                max_power,
                maximum_automated,
                relaxed_reserves=False,
                storage_equipment=False,
                thermal_equipment=False,
            )

    def add_constraints(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding constraints for wind unit {eq.name} at time {time}")
            max_power = eq._cached_forecast.get_value(time) if eq._cached_forecast else 0
            min_power = (1 - eq.maximum_curtailment_ratio.get_value(time)) * max_power
            maximum_automated = get_maximum_automated(eq)

            power_level_var = model.get_variable(f"{eq.name}_power_level_{time}")
            automated_reserves_up_var = model.get_variable(f"automated_reserves_up_{eq.name}_{time}")
            automated_reserves_down_var = model.get_variable(f"automated_reserves_down_{eq.name}_{time}")
            reserves_up_var = model.get_variable(f"reserves_up_{eq.name}_{time}")
            reserves_down_var = model.get_variable(f"reserves_down_{eq.name}_{time}")

            model.add_constraint(power_level_var <= max_power, f"power_max_{time}_{eq.name}")
            model.add_constraint(power_level_var >= min_power, f"power_min_{time}_{eq.name}")
            model.add_constraint(
                automated_reserves_up_var <= maximum_automated, f"automated_reserves_up_max_{time}_{eq.name}"
            )
            model.add_constraint(
                automated_reserves_down_var <= maximum_automated, f"automated_reserves_down_max_{time}_{eq.name}"
            )
            model.add_constraint(reserves_up_var <= max_power, f"reserves_up_max_{time}_{eq.name}")
            model.add_constraint(reserves_down_var <= max_power, f"reserves_down_max_{time}_{eq.name}")

    def add_objective(
        self, model: OptimisationModel, parameters: PortfolioOptimisationParameters, price_forecasts: dict = {}
    ):
        eq = self.equipment
        for time in eq.optimisation_time_window:
            cfg.logger.debug(f"Adding objective for wind unit {eq.name} at time {time}")
            power_level_var = model.get_variable(f"{eq.name}_power_level_{time}")
            model.add_objective(
                get_variable_cost(eq, time) * power_level_var * parameters.temporal.timestep.total_hours()
            )
