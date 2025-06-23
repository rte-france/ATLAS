"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas.enum import SolverStatus
from atlas.models.equipment.equipment import Equipment
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.enum import EquipmentType
from atlas.modules.portfolio_optimisation.initialisation.PO_portfolio import POPortfolio
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.constraint_builder import ConstraintBuilder
from atlas.modules.portfolio_optimisation.utils.equipment import EquipmentClassifier, EquipmentCollector
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.modules.portfolio_optimisation.utils.objective_builder import ObjectiveFunctionBuilder
from atlas.modules.portfolio_optimisation.utils.output_manager import OutputManager
from atlas.solver.solver_interface import OptimisationModel, SolutionInfo


class OptimalPlacementOptimizer:
    """Main class for optimal placement optimization using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

        # Initialize components
        self.equipment_classifier = EquipmentClassifier(parameters)
        self.equipment_collector = EquipmentCollector()
        self.objective_builder = ObjectiveFunctionBuilder(parameters)
        self.constraint_builder = ConstraintBuilder(parameters)
        self.output_manager = OutputManager(parameters)

    def _get_solver_name(self) -> str:
        """Map solver names from parameters to OR-Tools solver names."""
        solver_mapping = {
            "CPLEX": "CPLEX_MIXED_INTEGER_PROGRAMMING",
            "GUROBI": "GUROBI_MIXED_INTEGER_PROGRAMMING",
            "SCIP": "SCIP_MIXED_INTEGER_PROGRAMMING",
            "GLOP": "GLOP_LINEAR_PROGRAMMING",
            "CBC": "CBC_MIXED_INTEGER_PROGRAMMING",
        }

        solver_name = getattr(self.parameters, "solver", "SCIP")
        return solver_mapping.get(solver_name, "SCIP_MIXED_INTEGER_PROGRAMMING")

    def optimize(self, output_marker) -> list[str]:
        """
        Main optimization method.

        Args:
            output_marker: The output marker containing all equipment data

        Returns:
            List of status messages from the optimization process
        """
        cfg.logger.info("Starting optimal placement optimization")

        # Collect equipment by type
        self._collect_equipment(output_marker)

        # Perform optimization based on mode
        if self.parameters.is_portfolio_bidding:
            return self._optimize_portfolio_mode(output_marker)
        else:
            return self._optimize_unit_mode(output_marker)

    def _collect_equipment(self, output_marker):
        """Collect and classify all equipment."""
        self.equipment_collector.clear()

        # Collect thermic equipment
        for equipment in output_marker.Thermic.GetAllInstances():
            if self.equipment_classifier.should_manually_activate(equipment):
                set_manual_activation([equipment], self.parameters)
            elif self.parameters.is_portfolio_bidding:
                self.equipment_collector.add_equipment(EquipmentType.THERMIC, equipment)
            else:
                self._optimize_single_equipment(output_marker, equipment, EquipmentType.THERMIC)

        # Collect other equipment types
        self._collect_equipment_by_type(output_marker, "Hydraulic", EquipmentType.HYDRAULIC)
        self._collect_equipment_by_type(output_marker, "Storage", EquipmentType.STORAGE)
        self._collect_load_equipment(output_marker)
        self._collect_equipment_by_type(output_marker, "Wind", EquipmentType.WIND)
        self._collect_equipment_by_type(output_marker, "Photovoltaic", EquipmentType.PHOTOVOLTAIC)
        self._collect_equipment_by_type(
            output_marker, "OtherNonDispatchable", EquipmentType.NON_DISPATCHABLE_PRODUCTION
        )

    def _collect_equipment_by_type(self, output_marker, marker_attr: str, equipment_type: EquipmentType):
        """Generic method to collect equipment by type."""
        marker_collection = getattr(output_marker, marker_attr)

        for equipment in marker_collection.GetAllInstances():
            if self.equipment_classifier.should_manually_activate(equipment):
                set_manual_activation([equipment], self.parameters)
            elif self.parameters.is_portfolio_bidding:
                self.equipment_collector.add_equipment(equipment_type, equipment)
            else:
                self._optimize_single_equipment(output_marker, equipment, equipment_type)

    def _collect_load_equipment(self, output_marker):
        """Collect load equipment with special handling for PowerToGas."""
        for equipment in output_marker.Load.GetAllInstances():
            if self.equipment_classifier.should_manually_activate(equipment):
                set_manual_activation([equipment], self.parameters)
            elif self.parameters.is_portfolio_bidding:
                if equipment.LoadType == "PowerToGas":
                    self.equipment_collector.add_equipment(EquipmentType.DISPATCHABLE_LOAD, equipment)
                else:
                    self.equipment_collector.add_equipment(EquipmentType.NON_DISPATCHABLE_LOAD, equipment)
            else:
                load_type = (
                    EquipmentType.DISPATCHABLE_LOAD
                    if equipment.LoadType == "PowerToGas"
                    else EquipmentType.NON_DISPATCHABLE_LOAD
                )
                self._optimize_single_equipment(output_marker, equipment, load_type)

    def _optimize_portfolio_mode(self, output_marker) -> list[str]:
        """Optimize in portfolio bidding mode."""
        cfg.logger.info("Optimizing in portfolio bidding mode")

        return self._optimize_portfolio(
            output_marker,
            output_marker.Portfolio.AllInstances,
            self.equipment_collector.equipment_by_type,
        )

    def _optimize_unit_mode(self, output_marker) -> list[str]:
        """Optimize in unit-based mode."""
        cfg.logger.info("Optimizing in unit-based mode")
        return []

    def _optimize_single_equipment(self, output_marker, equipment: type[Equipment], equipment_type: EquipmentType):
        """Optimize a single equipment unit."""
        equipment_dict = {et: [] for et in EquipmentType}
        equipment_dict[equipment_type] = [equipment]

        self._optimize_portfolio(output_marker, [equipment.Portfolio], equipment_dict, single_equipment=equipment)

    def _optimize_portfolio(
        self,
        output_marker,
        portfolios: list,
        equipment_dict: dict[EquipmentType, list[type[Equipment]]],
        single_equipment=None,
    ) -> list[str]:
        """Optimize a portfolio or single equipment."""
        status_messages = []

        for portfolio in portfolios:
            # Skip excluded market areas
            if self.equipment_classifier.is_excluded_market_area(portfolio):
                self._handle_excluded_market_area(portfolio, single_equipment)
                continue

            # Filter equipment for this portfolio
            portfolio_equipment = self._filter_equipment_by_portfolio(equipment_dict, portfolio.name)

            # Skip if no equipment
            if not any(equipment_list for equipment_list in portfolio_equipment.values()):
                continue

            # Perform optimization
            solution_info = self._optimize_single_portfolio(
                output_marker, portfolio, portfolio_equipment, single_equipment
            )

            status_messages.append(f"{portfolio.name} ended with status {solution_info.status.value}")

        return status_messages

    def _optimize_single_portfolio(
        self,
        output_marker,
        portfolio: Portfolio,
        equipment_dict: dict[EquipmentType, list],
        single_equipment=None,
    ) -> SolutionInfo:
        """Optimize a single portfolio using OptimisationModel."""
        portfolio_name = single_equipment.name if single_equipment else portfolio.name

        cfg.logger.info(f"Optimizing portfolio: {portfolio_name}")

        # Create optimization model
        solver_name = self._get_solver_name()
        model = OptimisationModel(solver_name=solver_name, name=portfolio_name)

        try:
            # Create portfolio object
            Portfolio = self._create_Portfolio(portfolio, equipment_dict)

            # Build objective function
            objective_expr = self.objective_builder.build_objective(model, Portfolio, self.parameters.target_times)

            model.set_objective(objective_expr, direction="minimize")

            # Build and add constraints
            optimization_times = self._get_optimization_times()
            self.constraint_builder.build_and_add_constraints(model, Portfolio, optimization_times)

            # Solve problem
            time_limit = getattr(self.parameters, "time_out", 3600)
            solution_info = model.solve(time_limit=time_limit)

            cfg.logger.info(
                f"Portfolio {portfolio_name} optimization completed with status: {solution_info.status.name}"
            )

            # Export results
            if solution_info.status == SolverStatus.OPTIMAL:
                self._export_optimization_results(output_marker, model, Portfolio, solution_info)
            else:
                # Fallback to manual activation
                equipment_list = [single_equipment] if single_equipment else portfolio.GetChildren("Equipment")
                set_manual_activation(equipment_list, self.parameters)

            return solution_info

        except Exception as e:
            cfg.logger.error(f"Optimization failed for portfolio {portfolio_name}: {e}")

            # Fallback to manual activation
            equipment_list = [single_equipment] if single_equipment else portfolio.GetChildren("Equipment")
            set_manual_activation(equipment_list, self.parameters)

            # Return a failed solution info
            return SolutionInfo(
                status=SolverStatus.NOT_SOLVED,
                objective_value=None,
                solve_time=None,
                num_iterations=None,
            )

    def _export_optimization_results(
        self,
        output_marker,
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
            self.output_manager.export_results(output_marker, Portfolio, solution_info, variable_values)

        except Exception as e:
            cfg.logger.error(f"Failed to export results: {e}")

    def _create_Portfolio(self, portfolio: Portfolio, equipment_dict: dict[EquipmentType, list]) -> Portfolio:
        """Create and initialize Portfolio object."""
        Portfolio = POPortfolio(portfolio.name)

        # Get longest optimization period
        optimization_times = self._get_optimization_times()
        max_op_time = max(optimization_times.values(), key=len)

        # Initialize portfolio
        Portfolio.InitVariablesAndPreComputations(
            portfolio,
            equipment_dict[EquipmentType.THERMIC],
            equipment_dict[EquipmentType.HYDRAULIC],
            equipment_dict[EquipmentType.STORAGE],
            equipment_dict[EquipmentType.WIND],
            equipment_dict[EquipmentType.PHOTOVOLTAIC],
            equipment_dict[EquipmentType.NON_DISPATCHABLE_PRODUCTION],
            equipment_dict[EquipmentType.NON_DISPATCHABLE_LOAD],
            equipment_dict[EquipmentType.DISPATCHABLE_LOAD],
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
        self, equipment_dict: dict[EquipmentType, list[type[Equipment]]], portfolio: Portfolio
    ) -> dict[EquipmentType, list]:
        """Filter equipment dictionary to only include equipment from specified portfolio."""
        filtered_dict = {equipment_type: [] for equipment_type in EquipmentType}

        for equipment_type, equipment_list in equipment_dict.items():
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
