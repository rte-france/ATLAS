from __future__ import annotations

from pendulum import DateTime

from atlas.enum import LoadType
from atlas.models.equipment.load import Load
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.getters import get_maximum_power, get_minimum_power
from atlas.solver.solver_interface import OptimisationModel


class LoadPO(Load):
    load_type: LoadType

    def add_variables(self, model: OptimisationModel, parameters: PortfolioOptimisationParameters):
        """Build variables for load equipment."""

        for time in parameters.target_times:
            max_power = get_maximum_power(self, time, self.parameters.execution_date)

            model.add_continuous_variable(
                f"{self.name}_power_level_{time}",
                lower_bound=0,
                upper_bound=max_power,
            )

    def add_constraints(
        self,
        time: DateTime,
        model: OptimisationModel,
    ):
        """
        This function adds constraints and elements in the objective function related to load equipments.
        """

        power_level_var = model.get_variable(f"{self.name}_power_level_{time}")
        model.add_constraint(power_level_var >= get_maximum_power(self, time))
        model.add_constraint(power_level_var <= get_minimum_power(self, time))
