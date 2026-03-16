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
    """
    Portfolio-specific optimization model that inherits OR-Tools capabilities.

    :param portfolio: Portfolio to optimize
    :type portfolio: PortfolioPO
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :param solver_options: Solver configuration options
    :type solver_options: SolverOptions
    """

    def __init__(
        self, portfolio: PortfolioPO, parameters: PortfolioOptimisationParameters, solver_options: SolverOptions
    ):
        super().__init__(solver_name=parameters.solver.solver_name, name=portfolio.name, options=solver_options)
        self.portfolio = portfolio
        self.parameters = parameters

    def _prefetch_equipment_forecasts(self) -> None:
        """Pre-fetch forecasts for all equipment to avoid redundant get_forecast calls during model building."""
        cfg.logger.debug("Pre-fetching forecasts for all equipment...")

        for wind in self.portfolio.equipments.wind:
            wind.prefetch_forecasts(self.parameters.date.execution_date)

        for solar in self.portfolio.equipments.solar:
            solar.prefetch_forecasts(self.parameters.date.execution_date)

        for load in [*self.portfolio.equipments.dispatchable_load, *self.portfolio.equipments.non_dispatchable_load]:
            load.prefetch_forecasts(self.parameters.date.execution_date)

        for hydro in self.portfolio.equipments.hydro:
            hydro.prefetch_forecasts(
                self.parameters.date.execution_date, self.parameters.date.timestep, self.parameters.date.start_date
            )

        for storage in self.portfolio.equipments.storage:
            storage.prefetch_forecasts(self.parameters.date.execution_date, self.parameters.init_battery_time)

        cfg.logger.debug("Completed pre-fetching forecasts.")

    def build(self, time_window: list[DateTime]) -> None:
        """
        Build the optimization model by adding variables, constraints, and objectives.

        :param time_window: List of time periods to optimize over
        :type time_window: list[DateTime]
        """
        cfg.logger.info(f"Building optimisation model for portfolio: {self.portfolio.name} ..")

        self._prefetch_equipment_forecasts()

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
            thermal.add_daily_energy_constraint(model=self, timestep=self.parameters.date.timestep)

        for storage in self.portfolio.equipments.storage:
            storage.add_cycle_balance_constraint(model=self)

            cfg.logger.debug(f"Completed optimisation model at time: {time}")

        cfg.logger.info(f"Completed optimisation model for portfolio: {self.portfolio.name}.")
