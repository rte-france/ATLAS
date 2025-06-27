"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from itertools import groupby

import atlas.config as cfg
from atlas.enum import SolverStatus
from atlas.models.equipment.equipment import Equipment
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.constraint_builder import ConstraintBuilder
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.modules.portfolio_optimisation.utils.objective_builder import ObjectiveFunctionBuilder
from atlas.solver.solver_interface import OptimisationModel, SolutionInfo


class OptimalPlacementOptimizer:
    """Main class for optimal placement optimization using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

        # Initialize components

        self.portfolios: dict[str, dict[str, list[type[Equipment]]]] = {}
        self.objective_builder = ObjectiveFunctionBuilder(parameters)
        self.constraint_builder = ConstraintBuilder(parameters)

    def optimize(self, input_dataset: PortfolioOptimisationInputDataset) -> list[str]:
        """
        Main optimization method.
        """
        cfg.logger.info("Starting optimal placement optimization")

        portfolios = self._create_portfolios(input_dataset)

        for portfolio in input_dataset.portfolio:
            self._optimize_portfolio(input_dataset, portfolios[portfolio.name], portfolio.name)

    def _create_portfolios(self, input_dataset: PortfolioOptimisationInputDataset):
        """Collect and classify all equipment into portfolios"""

        # Aplatir avec le type d'équipement
        all_equipments_with_type = [
            (equipment, equipment_type)
            for equipment_type, equipment_list in input_dataset.equipments.items()
            for equipment in equipment_list
        ]

        # Trier par portfolio puis par type
        all_equipments_with_type.sort(key=lambda x: (x[0].portfolio.name, x[1]))

        # Double groupby : portfolio puis type
        portfolios = {}
        for portfolio_name, portfolio_items in groupby(all_equipments_with_type, key=lambda x: x[0].portfolio.name):
            portfolio_list = list(portfolio_items)

            equipment_by_type = {}
            for equipment_type, type_items in groupby(portfolio_list, key=lambda x: x[1]):
                equipment_by_type[equipment_type] = [equipment for equipment, _ in type_items]

            portfolios[portfolio_name] = equipment_by_type

        return portfolios

    def _optimize_portfolio(
        self,
        input_dataset: PortfolioOptimisationInputDataset,
        portfolio: dict[str, list[type[Equipment]]],
        portfolio_name: str,
        solver_name: str,
    ) -> SolutionInfo:
        """Optimize a single portfolio using OptimisationModel."""

        cfg.logger.info(f"Optimizing portfolio: {portfolio_name}")

        # Create optimization model
        model = OptimisationModel(solver_name=solver_name, name=portfolio_name)

        try:
            optimization_times = self._get_optimization_times()
            self.constraint_builder.build_constraints(portfolio, portfolio_name, optimization_times, model)

            objective_expr = self.objective_builder.build_objective(model, portfolio, self.parameters.target_times)
            model.set_objective(objective_expr, direction="minimize")

            solution_info = model.solve(time_limit=self.parameters.timeout)

            cfg.logger.info(
                f"Portfolio {portfolio_name} optimization completed with status: {solution_info.status.name}"
            )

            if solution_info.status == SolverStatus.OPTIMAL:
                self._export_optimization_results(input_dataset, model, portfolio, solution_info)
            else:
                pass

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

    def _export_optimization_results(
        self,
        input_dataset: PortfolioOptimisationInputDataset,
        model: OptimisationModel,
        Portfolio: Portfolio,
        solution_info: SolutionInfo,
    ):
        """Export optimization results using the model's variable values."""
        try:
            # Extract variable values from the solved model
            variable_values = {}
            for var_name in model.variables_name:
                variable_values[var_name] = model.get_variable_value(var_name)

            # Use output manager to export results
            # You may need to adapt this based on how OutputManager expects the data
            self.output_manager.export_results(input_dataset, Portfolio, solution_info, variable_values)

        except Exception as e:
            cfg.logger.error(f"Failed to export results: {e}")

    def _get_optimization_times(self) -> dict[str, list]:
        """Get all optimization time periods."""
        return {
            "op_times": self.parameters.op_times,
            "thermal_op_times": self.parameters.thermal_op_times,
            "hydraulic_op_times": self.parameters.hydraulic_op_times,
            "battery_op_times": self.parameters.battery_op_times,
            "phs_op_times": self.parameters.phs_op_times,
            "ev_op_times": self.parameters.ev_op_times,
        }

    def _handle_excluded_market_area(self, portfolio: Portfolio, single_equipment=None):
        """Handle portfolios in excluded market areas."""
        if self.parameters.is_portfolio_bidding:
            cfg.logger.warning(f"Portfolio {portfolio.name} is in excluded market area and will not be optimized")
            set_manual_activation(portfolio.GetChildren("Equipment"), self.parameters)
        else:
            cfg.logger.warning(
                f"Equipment {single_equipment.name} is in excluded market area and will not be optimized"
            )
            set_manual_activation([single_equipment], self.parameters)
