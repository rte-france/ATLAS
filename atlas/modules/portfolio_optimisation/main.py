"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

import atlas.config as cfg
from atlas.enum import LoadType, SolverStatus
from atlas.models.equipment.equipment import Equipment
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.enum import EquipmentType
from atlas.modules.portfolio_optimisation.initialisation.PO_portfolio import POPortfolio
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.constraint_builder import ConstraintBuilder
from atlas.modules.portfolio_optimisation.utils.equipment import is_excluded_market_area, should_manually_activate
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.modules.portfolio_optimisation.utils.objective_builder import ObjectiveFunctionBuilder
from atlas.modules.portfolio_optimisation.utils.output_manager import OutputManager
from atlas.solver.solver_interface import OptimisationModel, SolutionInfo


class OptimalPlacementOptimizer:
    """Main class for optimal placement optimization using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

        # Initialize components

        self.equipments: dict[str, list[type[Equipment]]] = {}
        self.objective_builder = ObjectiveFunctionBuilder(parameters)
        self.constraint_builder = ConstraintBuilder(parameters)
        self.output_manager = OutputManager(parameters)

    def optimize(self, input_dataset: PortfolioOptimisationInputDataset) -> list[str]:
        """
        Main optimization method.

        Args:
            input_dataset: The output marker containing all equipment data

        Returns:
            List of status messages from the optimization process
        """
        cfg.logger.info("Starting optimal placement optimization")

        self._collect_equipment(input_dataset)

        # Perform optimization based on mode
        if self.parameters.is_portfolio_bidding:
            return self._optimize_portfolio_mode(input_dataset)
        else:
            return self._optimize_unit_mode(input_dataset)

    def _collect_equipment(self, input_dataset: PortfolioOptimisationInputDataset):
        """Collect and classify all equipment."""
        self._collect_equipment_thermal(input_dataset)
        self._collect_equipment_by_type(input_dataset, "hydro")
        self._collect_equipment_by_type(input_dataset, "storage")
        self._collect_load_equipment(input_dataset)
        self._collect_equipment_by_type(input_dataset, "wind")
        self._collect_equipment_by_type(input_dataset, "solar")
        self._collect_equipment_by_type(input_dataset, "other_non_dispatchable")

    def _collect_equipment_thermal(self, input_dataset: PortfolioOptimisationInputDataset):
        for equipment in input_dataset.thermal:
            if should_manually_activate(equipment):
                set_manual_activation([equipment], self.parameters)
            elif self.parameters.is_portfolio_bidding:
                self.equipments["thermal"].append(equipment)
            else:
                self._optimize_single_equipment(input_dataset, equipment, "thermal")

    def _collect_equipment_by_type(self, input_dataset: PortfolioOptimisationInputDataset, equipment_type: str):
        """Generic method to collect equipment by type."""

        for equipment in cast(list[type[Equipment]], getattr(input_dataset, equipment_type)):
            if should_manually_activate(equipment):
                set_manual_activation([equipment], self.parameters)
            elif self.parameters.is_portfolio_bidding:
                self.equipments[equipment_type].append(equipment)
            else:
                self._optimize_single_equipment(input_dataset, equipment, equipment_type)

    def _collect_load_equipment(self, input_dataset: PortfolioOptimisationInputDataset):
        for equipment in input_dataset.load:
            if should_manually_activate(equipment):
                set_manual_activation([equipment], self.parameters)
            elif self.parameters.is_portfolio_bidding:
                if equipment.load_type == LoadType.POWER_TO_GAS:
                    self.equipments["dispatchable_load"].append(equipment)
                else:
                    self.equipments["non_dispatchable_load"].append(equipment)
            else:
                equipment_type = (
                    "dispatchable_load" if equipment.LoadType == LoadType.POWER_TO_GAS else "non_dispatchable_load"
                )
                self._optimize_single_equipment(input_dataset, equipment, equipment_type)

    def _optimize_portfolio_mode(self, input_dataset: PortfolioOptimisationInputDataset) -> list[str]:
        """Optimize in portfolio bidding mode."""
        cfg.logger.info("Optimizing in portfolio bidding mode")

        return self._optimize_portfolio(
            input_dataset,
            input_dataset.portfolio,
            self.equipments,
        )

    def _optimize_unit_mode(self, input_dataset: PortfolioOptimisationInputDataset) -> list[str]:
        """Optimize in unit-based mode."""
        cfg.logger.info("Optimizing in unit-based mode")
        return []

    def _optimize_single_equipment(
        self,
        input_dataset: PortfolioOptimisationInputDataset,
        equipment: type[Equipment],
        equipment_type: str,
    ):
        """Optimize a single equipment unit."""
        equipments = {equipment_type: [equipment]}

        self._optimize_portfolio(input_dataset, [equipment.portfolio], equipments, single_equipment=equipment)

    def _optimize_portfolio(
        self,
        input_dataset: PortfolioOptimisationInputDataset,
        portfolios: list[Portfolio],
        equipments: dict[str, list[type[Equipment]]],
        single_equipment: type[Equipment] | None = None,
    ) -> list[str]:
        """Optimize a portfolio or single equipment."""

        for portfolio in portfolios:
            if is_excluded_market_area(portfolio):
                self._handle_excluded_market_area(portfolio, single_equipment)
                continue

            portfolio_equipment = self._filter_equipment_by_portfolio(equipments, portfolio.name)

            if not any(equipment_list for equipment_list in portfolio_equipment.values()):
                continue

            self._optimize_single_portfolio(input_dataset, portfolio, portfolio_equipment, single_equipment)

    def _optimize_single_portfolio(
        self,
        input_dataset: PortfolioOptimisationInputDataset,
        portfolio: Portfolio,
        equipments: dict[str, list[type[Equipment]]],
        solver_name: str,
        single_equipment=None,
    ) -> SolutionInfo:
        """Optimize a single portfolio using OptimisationModel."""
        portfolio_name = single_equipment.name if single_equipment else portfolio.name

        cfg.logger.info(f"Optimizing portfolio: {portfolio_name}")

        # Create optimization model
        model = OptimisationModel(solver_name=solver_name, name=portfolio_name)

        try:
            # Create portfolio object
            Portfolio = self._create_portfolio(portfolio, equipments)

            # Build and add constraints
            optimization_times = self._get_optimization_times()
            self.constraint_builder.build_constraints(model, Portfolio, optimization_times)

            # Build objective function
            objective_expr = self.objective_builder.build_objective(model, Portfolio, self.parameters.target_times)
            model.set_objective(objective_expr, direction="minimize")

            solution_info = model.solve(time_limit=self.parameters.time_out)

            cfg.logger.info(
                f"Portfolio {portfolio_name} optimization completed with status: {solution_info.status.name}"
            )

            if solution_info.status == SolverStatus.OPTIMAL:
                self._export_optimization_results(input_dataset, model, Portfolio, solution_info)
            else:
                equipment_list = [single_equipment] if single_equipment else equipments
                set_manual_activation(equipment_list, self.parameters)

            return solution_info

        except Exception as e:
            cfg.logger.error(f"Optimization failed for portfolio {portfolio_name}: {e}")

            # Fallback to manual activation
            equipment_list = [single_equipment] if single_equipment else equipments
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

    def _create_portfolio(self, portfolio: Portfolio, equipments: dict[str, list[type[Equipment]]]) -> Portfolio:
        """Create and initialize Portfolio object."""
        Portfolio = POPortfolio(portfolio.name)

        # Get longest optimization period
        optimization_times = self._get_optimization_times()
        max_op_time = max(optimization_times.values(), key=len)

        # Initialize portfolio
        Portfolio.init_variables_and_pre_computations(
            portfolio,
            equipments[EquipmentType.THERMIC],
            equipments[EquipmentType.HYDRAULIC],
            equipments[EquipmentType.STORAGE],
            equipments[EquipmentType.WIND],
            equipments[EquipmentType.PHOTOVOLTAIC],
            equipments[EquipmentType.NON_DISPATCHABLE_PRODUCTION],
            equipments[EquipmentType.NON_DISPATCHABLE_LOAD],
            equipments[EquipmentType.DISPATCHABLE_LOAD],
            max_op_time,
            self.parameters,
        )

        return Portfolio

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

    def _filter_equipment_by_portfolio(
        self, equipments: dict[str, list[type[Equipment]]], portfolio: Portfolio
    ) -> dict[EquipmentType, list]:
        """Filter equipment dictionary to only include equipment from specified portfolio."""
        filtered_dict = {}
        for equipment_type, equipment_list in equipments.items():
            filtered_dict[equipment_type] = []
            for equipment in equipment_list:
                if equipment.portfolio == portfolio:
                    filtered_dict[equipment_type].append(equipment)

        return filtered_dict

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
