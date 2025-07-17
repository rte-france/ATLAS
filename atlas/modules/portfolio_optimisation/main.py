"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

from pendulum import DateTime

import atlas.config as cfg
from atlas.enum import SolverStatus
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.optimisation.constraint_builder import ConstraintBuilder
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.solver.solver_interface import OptimisationModel, SolutionInfo


class PortfolioOptimisationModel:
    """Main class for optimal placement optimization using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters
        self.constraint_builder = ConstraintBuilder(parameters)

    def optimize(self, input_dataset: PortfolioOptimisationInputDataset) -> None:
        """
        Main optimization method.
        """
        cfg.logger.info("Starting optimal placement optimization")

        if self.parameters.is_portfolio_bidding:
            for portfolio in input_dataset.portfolios:
                self._optimize_portfolio(
                    portfolio=portfolio,
                    solver_name=self.parameters.solver_name,
                    max_optimisation_times=input_dataset.max_optimisation_times,
                    optimisation_times=input_dataset.optimisation_times,
                )
            for portfolio in input_dataset.portfolios_manual_activation:
                self._optimize_portfolio_manual_activated(
                    portfolio=input_dataset.portfolios_manual_activation[portfolio.name],
                )
        else:
            for portfolio in input_dataset.portfolios:
                for equipment_type, list_equipment in portfolio.equipments.items():
                    for equipment in list_equipment:
                        equipment_portfolio = PortfolioPO(name=equipment.name, equipments={equipment_type: [equipment]})

                        self._optimize_portfolio(
                            portfolio=equipment_portfolio,
                            solver_name=self.parameters.solver_name,
                            max_optimisation_times=input_dataset.max_optimisation_times,
                            optimisation_times=input_dataset.optimisation_times,
                        )

            for portfolio_manual in input_dataset.portfolios_manual_activation:
                for equipment_type, list_equipment in portfolio_manual.equipments.items():
                    for equipment in list_equipment:
                        equipment_portfolio = PortfolioPO(name=equipment.name, equipments={equipment_type: [equipment]})

                    self._optimize_portfolio_manual_activated(
                        portfolio=equipment_portfolio,
                    )

    def _optimize_portfolio(
        self,
        portfolio: PortfolioPO,
        solver_name: str,
        max_optimisation_times: list[DateTime],
        optimisation_times: dict[str, list[DateTime]],
    ) -> SolutionInfo:
        """Optimize a single portfolio using OptimisationModel."""

        cfg.logger.info(f"Optimizing portfolio: {portfolio.name}")

        model = OptimisationModel(solver_name=solver_name, name=portfolio.name)

        portfolio.add_variables(model, self.parameters.target_times, self.parameters)
        for equipment_type in portfolio.equipments:
            for equipment in cast(
                list[HydroPO | LoadPO | WindPO | StoragePO | ThermalPO | OtherNonDispatchablePO],
                portfolio.equipments.get(equipment_type, []),
            ):
                equipment.add_variables(model, self.parameters)

        try:
            self.constraint_builder.build_constraints(portfolio, max_optimisation_times, optimisation_times, model)
            objective_expr = self.objective_builder.build_objective(model, portfolio, self.parameters.target_times)
            model.set_objective(objective_expr, direction="minimize")

            solution_info = model.solve()

            cfg.logger.info(
                f"Portfolio {portfolio.name} optimization completed with status: {solution_info.status.name}"
            )

            # if solution_info.status == SolverStatus.OPTIMAL:
            #     self._export_optimization_results(input_dataset, model, portfolio, solution_info)
            # else:
            #     pass

            return solution_info

        except Exception as e:
            cfg.logger.error(f"Optimization failed for portfolio {portfolio.name}: {e}")

            equipment_list = [
                portfolio.equipments[t][equipment]
                for t in portfolio.equipments
                for equipment in portfolio.equipments[t]
            ]
            set_manual_activation(equipment_list, self.parameters)

            return SolutionInfo(
                status=SolverStatus.NOT_SOLVED,
                objective_value=None,
                solve_time=None,
                num_iterations=None,
            )

    def _optimize_portfolio_manual_activated(self, portfolio: PortfolioPO):
        pass
