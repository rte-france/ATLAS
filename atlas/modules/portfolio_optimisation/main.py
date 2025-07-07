"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.enum import SolverStatus
from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.model.constraint_builder import ConstraintBuilder
from atlas.modules.portfolio_optimisation.model.objective_builder import ObjectiveFunctionBuilder
from atlas.modules.portfolio_optimisation.model.variable_builder import VariableBuilder
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.solver.solver_interface import OptimisationModel, SolutionInfo


class PortfolioOptimisationModel:
    """Main class for optimal placement optimization using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters
        self.portfolios: dict[str, dict[str, list[type[Equipment]]]] = {}
        self.objective_builder = ObjectiveFunctionBuilder(parameters)
        self.constraint_builder = ConstraintBuilder(parameters)
        self.variable_builder = VariableBuilder(parameters)

    def optimize(self, input_dataset: PortfolioOptimisationInputDataset) -> list[str]:
        """
        Main optimization method.
        """
        cfg.logger.info("Starting optimal placement optimization")

        if self.parameters.is_portfolio_bidding:
            for portfolio in input_dataset.portfolios:
                self._optimize_portfolio(
                    portfolio=input_dataset.portfolios[portfolio.name],
                    portfolio_name=portfolio.name,
                    solver_name=self.parameters.solver_name,
                    max_optimisation_times=input_dataset.max_optimisation_times,
                    optimisation_times=input_dataset.optimisation_times,
                )
                if portfolio.name in input_dataset.portfolios_manual_activation:
                    self._optimize_portfolio_manual_activated(
                        portfolio_name=portfolio.name,
                        portfolio_manual_activation=input_dataset.portfolios_manual_activation[portfolio.name],
                    )
        else:
            for _, portfolio in input_dataset.portfolios.items():
                for equipment_type, list_equipment in portfolio.items():
                    for equipment in list_equipment:
                        equipment_portfolio = {equipment_type: [equipment]}
                        equipment_portfolio_name = f"{equipment_type}_{equipment.name}"

                        self._optimize_portfolio(
                            portfolio=equipment_portfolio,
                            portfolio_name=equipment_portfolio_name,
                            solver_name=self.parameters.solver_name,
                            max_optimisation_times=input_dataset.max_optimisation_times,
                            optimisation_times=input_dataset.optimisation_times,
                        )

            for _, portfolio_manual in input_dataset.portfolios_manual_activation.items():
                for equipment_type, list_equipment in portfolio_manual.items():
                    for equipment in list_equipment:
                        equipment_portfolio = {equipment_type: [equipment]}
                        equipment_portfolio_name = f"{equipment_type}_{equipment.name}_manual"

                        self._optimize_portfolio_manual_activated(
                            portfolio_name=equipment_portfolio_name,
                            portfolio_manual_activation=equipment_portfolio,
                        )

    def _optimize_portfolio(
        self,
        portfolio: dict[str, list[type[Equipment]]],
        portfolio_name: str,
        solver_name: str,
        max_optimisation_times: list[DateTime],
        optimisation_times: dict[str, list[DateTime]],
    ) -> SolutionInfo:
        """Optimize a single portfolio using OptimisationModel."""

        cfg.logger.info(f"Optimizing portfolio: {portfolio_name}")

        # Create optimization model
        model = OptimisationModel(solver_name=solver_name, name=portfolio_name)
        self.variable_builder.build_variables(model, portfolio_name, portfolio)

        try:
            self.constraint_builder.build_constraints(
                portfolio, portfolio_name, max_optimisation_times, optimisation_times, model
            )
            objective_expr = self.objective_builder.build_objective(model, portfolio, self.parameters.target_times)
            model.set_objective(objective_expr, direction="minimize")

            solution_info = model.solve()

            cfg.logger.info(
                f"Portfolio {portfolio_name} optimization completed with status: {solution_info.status.name}"
            )

            # if solution_info.status == SolverStatus.OPTIMAL:
            #     self._export_optimization_results(input_dataset, model, portfolio, solution_info)
            # else:
            #     pass

            return solution_info

        except Exception as e:
            cfg.logger.error(f"Optimization failed for portfolio {portfolio_name}: {e}")

            equipment_list = [portfolio[t][equipment] for t in portfolio for equipment in portfolio[t]]
            set_manual_activation(equipment_list, self.parameters)

            return SolutionInfo(
                status=SolverStatus.NOT_SOLVED,
                objective_value=None,
                solve_time=None,
                num_iterations=None,
            )

    def _optimize_portfolio_manual_activated(
        self, portfolio_manual_activation: dict[str, list[type[Equipment]]], portfolio_name: str
    ):
        pass
