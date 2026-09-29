"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.steps.portfolio import PortfolioStep
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
        self._step = PortfolioStep(portfolio)

    def build(self) -> None:
        """Build the optimization model by adding variables, constraints, and objectives."""
        cfg.logger.info(f"Building optimisation model for portfolio: {self.portfolio.name} ..")

        self._step.add_variables(self, self.parameters)
        self._step.add_constraints(self, self.parameters)
        self._step.add_objective(self, self.parameters)

        cfg.logger.info(f"Completed optimisation model for portfolio: {self.portfolio.name}.")
