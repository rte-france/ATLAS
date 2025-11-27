"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


class PortfolioOptimisationModel(OptimisationModel):
    """Portfolio-specific optimization model that inherits OR-Tools capabilities."""

    def __init__(
        self, portfolio: PortfolioPO, parameters: PortfolioOptimisationParameters, solver_options: SolverOptions
    ):
        super().__init__(solver_name=parameters.solver_name, name=portfolio.name, options=solver_options)
        self.portfolio = portfolio
        self.parameters = parameters

    def build_model(self, time_window: list[DateTime]) -> None:
        """Build the optimization model by adding variables, constraints, and objectives."""
        cfg.logger.info(f"Building optimisation model for portfolio: {self.portfolio.name} ..")

        # Add initial conditions for thermal equipment
        for thermal in self.portfolio.equipments.thermal:
            thermal.add_initial_conditions(self, self.parameters)

        for time in time_window:
            cfg.logger.debug(f"Building optimisation model at time: {time}..")

            self.portfolio.add_variables(self, time, self.parameters)
            price_forecast = self.portfolio.get_price_forecast(time, self.parameters)

            for _, equipment_list in self.portfolio.equipments.iter_by_type_for_optimisation():
                for equipment in equipment_list:
                    equipment.add_variables(self, time, self.parameters)
                    equipment.add_constraints(self, time, self.parameters)
                    equipment.add_objective(
                        model=self, time=time, parameters=self.parameters, price_forecast=price_forecast or 0.0
                    )

            self.portfolio.add_constraints(self, time, self.parameters)
            self.portfolio.add_objective(self, time, self.parameters)

        for thermal in self.portfolio.equipments.thermal:
            thermal.add_daily_energy_constraint(model=self, timestep=self.parameters.timestep)

        for storage in self.portfolio.equipments.storage:
            storage.add_cycle_balance_constraint(model=self)

            cfg.logger.debug(f"Completed optimisation model at time: {time}")

        cfg.logger.info(f"Completed optimisation model for portfolio: {self.portfolio.name}.")
