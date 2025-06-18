"""
Energy Portfolio Optimization Module

This module provides optimal placement and unit commitment functionality for
energy portfolios containing various types of generation, storage, and load equipment.
"""

from dataclasses import dataclass
from typing import Any

from pendulum import DateTime

import atlas.config as cfg
from atlas.models.equipment.equipment import Equipment
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation import Portfolio
from atlas.modules.portfolio_optimisation.enum import EquipmentType, SolverStatus
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.constraint_builder import ConstraintBuilder
from atlas.modules.portfolio_optimisation.utils.equipment import (
    EquipmentClassifier,
    EquipmentCollector,
)
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.modules.portfolio_optimisation.utils.output_manager import OutputManager
from atlas.solver.solver_interface import OptimisationModel, SolutionInfo


@dataclass
class OptimizationResults:
    """Results from the optimization process."""

    status: SolverStatus
    objective_value: float
    portfolio_name: str
    equipment_name: str | None = None
    solve_time: float | None = None
    gap: float | None = None

    @classmethod
    def from_solution_info(cls, solution_info: SolutionInfo, portfolio_name: str, equipment_name: str = None):
        """Create OptimizationResults from SolutionInfo."""
        # Map SolverStatus from OptimisationModel to portfolio optimization SolverStatus
        status_mapping = {
            solution_info.status: SolverStatus.OPTIMAL
            if solution_info.status.name == "OPTIMAL"
            else SolverStatus.FEASIBLE
            if solution_info.status.name == "FEASIBLE"
            else SolverStatus.INFEASIBLE
            if solution_info.status.name == "INFEASIBLE"
            else SolverStatus.UNBOUNDED
            if solution_info.status.name == "UNBOUNDED"
            else SolverStatus.NOT_SOLVED
        }

        return cls(
            status=status_mapping.get(solution_info.status, SolverStatus.NOT_SOLVED),
            objective_value=solution_info.objective_value or 0.0,
            portfolio_name=portfolio_name,
            equipment_name=equipment_name,
            solve_time=float(solution_info.solve_time.replace("s", "")) if solution_info.solve_time else None,
            gap=None,  # Gap not directly available from OR-Tools
        )


class SolverManager:
    """Manages the optimization solver using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters
        self.solver_name = self._get_solver_name()

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

    def create_optimization_problem(self, problem_name: str) -> OptimisationModel:
        """Create a new optimization problem."""
        return OptimisationModel(solver_name=self.solver_name, name=problem_name)

    def solve_problem(self, model: OptimisationModel) -> OptimizationResults:
        """Solve the optimization problem."""
        # Set solver parameters
        time_limit = getattr(self.parameters, "time_out", 3600)

        # Solve the problem
        solution_info = model.solve(time_limit=time_limit)

        # Convert to OptimizationResults
        return OptimizationResults.from_solution_info(
            solution_info=solution_info, portfolio_name=model.name or "Unknown"
        )


class ObjectiveFunctionBuilder:
    """Builds the optimization objective function using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def build_objective(self, model: OptimisationModel, portfolio: Portfolio, target_times: list) -> Any:
        """Build the complete objective function as OR-Tools expression."""
        objective_terms = []

        for time in target_times:
            # Add imbalance costs
            objective_terms.extend(self._get_imbalance_cost_terms(model, portfolio, time))

            # Add reserve penalties
            objective_terms.extend(self._get_reserve_penalty_terms(model, portfolio, time))

        # Sum all terms into a single expression
        if objective_terms:
            return sum(objective_terms)
        else:
            # Return zero expression if no terms
            dummy_var = model.add_continuous_variable("dummy_objective", 0, 0)
            return dummy_var

    def _get_imbalance_cost_terms(self, model: OptimisationModel, portfolio: Portfolio, time) -> list[Any]:
        """Get imbalance cost terms as OR-Tools expressions."""
        time_factor = self.parameters.time_step / 60.0
        terms = []

        # Get variables from portfolio (these would need to be OR-Tools variables)
        small_imbal_up = self._get_or_create_variable(model, f"small_imbal_up_{time}")
        small_imbal_down = self._get_or_create_variable(model, f"small_imbal_down_{time}")
        large_imbal_up = self._get_or_create_variable(model, f"large_imbal_up_{time}")
        large_imbal_down = self._get_or_create_variable(model, f"large_imbal_down_{time}")

        # Small imbalance costs
        if hasattr(portfolio, "imbal_price_up") and time in portfolio.imbal_price_up:
            terms.append(portfolio.imbal_price_up[time] * small_imbal_up * time_factor)

        if hasattr(portfolio, "imbal_price_down") and time in portfolio.imbal_price_down:
            terms.append(-portfolio.imbal_price_down[time] * small_imbal_down * time_factor)

        # Large imbalance costs
        if hasattr(portfolio, "large_imbal_price_up") and time in portfolio.large_imbal_price_up:
            terms.append(portfolio.large_imbal_price_up[time] * large_imbal_up * time_factor)

        if hasattr(portfolio, "large_imbal_price_down") and time in portfolio.large_imbal_price_down:
            terms.append(-portfolio.large_imbal_price_down[time] * large_imbal_down * time_factor)

        return terms

    def _get_reserve_penalty_terms(self, model: OptimisationModel, portfolio: Portfolio, time: DateTime) -> list[Any]:
        """Get reserve penalty terms as OR-Tools expressions."""
        time_factor = self.parameters.time_step / 60.0
        terms = []

        # Get or create reserve variables
        contracted_diff_up = self._get_or_create_variable(model, f"contracted_diff_up_{time}")
        contracted_diff_down = self._get_or_create_variable(model, f"contracted_diff_down_{time}")
        auto_contracted_diff_up = self._get_or_create_variable(model, f"auto_contracted_diff_up_{time}")
        auto_contracted_diff_down = self._get_or_create_variable(model, f"auto_contracted_diff_down_{time}")

        # Manual reserve penalties
        manual_penalty = getattr(self.parameters, "manual_unprocured_reserves_penalty", 1000)
        terms.append(manual_penalty * time_factor * contracted_diff_up)
        terms.append(manual_penalty * time_factor * contracted_diff_down)

        # Automated reserve penalties
        auto_penalty = getattr(self.parameters, "automated_unprocured_reserves_penalty", 1000)
        terms.append(auto_penalty * time_factor * auto_contracted_diff_up)
        terms.append(auto_penalty * time_factor * auto_contracted_diff_down)

        return terms

    def _get_or_create_variable(self, model: OptimisationModel, var_name: str) -> Any:
        """Get existing variable or create new one."""
        try:
            return model.get_variable(var_name)
        except ValueError:
            # Create new continuous variable if it doesn't exist
            return model.add_continuous_variable(var_name, lower_bound=0.0)


class ConstraintAdapter:
    """Adapts constraint building for OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters
        self.constraint_builder = ConstraintBuilder(parameters)

    def build_and_add_constraints(self, model: OptimisationModel, Portfolio: Portfolio, optimization_times: dict):
        """Build and add all constraints to the model."""
        # Get constraints from original constraint builder
        constraint_list, global_constraint_list = self.constraint_builder.build_constraints(
            Portfolio, optimization_times
        )

        # Convert and add constraints to OptimisationModel
        self._add_converted_constraints(model, constraint_list, "constraint")
        self._add_converted_constraints(model, global_constraint_list, "global_constraint")

    def _add_converted_constraints(self, model: OptimisationModel, constraint_list: list, prefix: str):
        """Convert API constraints to OR-Tools constraints and add to model."""
        for i, constraint in enumerate(constraint_list):
            constraint_name = f"{prefix}_{i}"

            # This is a placeholder - you'll need to implement the actual conversion
            # based on how your original constraints are structured
            try:
                # Convert API constraint to OR-Tools constraint
                or_tools_constraint = self._convert_constraint(constraint)
                model.add_constraint(or_tools_constraint, constraint_name)
            except Exception as e:
                cfg.logger.warning(f"Could not convert constraint {constraint_name}: {e}")

    def _convert_constraint(self, api_constraint) -> Any:
        """Convert API constraint to OR-Tools constraint."""
        # This is a placeholder implementation
        # You'll need to implement the actual conversion logic based on your API constraint format

        # For now, return a dummy constraint
        # In practice, you'd parse the API constraint and create equivalent OR-Tools expressions
        raise NotImplementedError("Constraint conversion needs to be implemented based on your API constraint format")


class OptimalPlacementOptimizer:
    """Main class for optimal placement optimization using OptimisationModel."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

        # Initialize components
        self.equipment_classifier = EquipmentClassifier(parameters)
        self.equipment_collector = EquipmentCollector()
        self.solver_manager = SolverManager(parameters)
        self.objective_builder = ObjectiveFunctionBuilder(parameters)
        self.constraint_adapter = ConstraintAdapter(parameters)
        self.output_manager = OutputManager(parameters)

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
            result = self._optimize_single_portfolio(output_marker, portfolio, portfolio_equipment, single_equipment)

            status_messages.append(f"{portfolio.name} ended with status {result.status.value}")

        return status_messages

    def _optimize_single_portfolio(
        self,
        output_marker,
        portfolio: Portfolio,
        equipment_dict: dict[EquipmentType, list],
        single_equipment=None,
    ) -> OptimizationResults:
        """Optimize a single portfolio using OptimisationModel."""
        portfolio_name = single_equipment.name if single_equipment else portfolio.name

        cfg.logger.info(f"Optimizing portfolio: {portfolio_name}")

        # Create optimization model
        model = self.solver_manager.create_optimization_problem(portfolio_name)

        try:
            # Create portfolio object
            Portfolio = self._create_Portfolio(portfolio, equipment_dict)

            # Build objective function
            objective_expr = self.objective_builder.build_objective(model, Portfolio, self.parameters.target_times)

            # Set objective
            model.set_objective(objective_expr, direction="minimize")  # or "maximize" based on your problem

            # Build and add constraints
            optimization_times = self._get_optimization_times()
            self.constraint_adapter.build_and_add_constraints(model, Portfolio, optimization_times)

            # Solve problem
            result = self.solver_manager.solve_problem(model)

            cfg.logger.info(f"Portfolio {portfolio_name} optimization completed with status: {result.status.value}")

            # Export results
            if result.status == SolverStatus.OPTIMAL:
                self._export_optimization_results(output_marker, model, Portfolio, result)
            else:
                # Fallback to manual activation
                equipment_list = [single_equipment] if single_equipment else portfolio.GetChildren("Equipment")
                set_manual_activation(equipment_list, self.parameters)

            return result

        except Exception as e:
            cfg.logger.error(f"Optimization failed for portfolio {portfolio_name}: {e}")

            # Fallback to manual activation
            equipment_list = [single_equipment] if single_equipment else portfolio.GetChildren("Equipment")
            set_manual_activation(equipment_list, self.parameters)

            return OptimizationResults(
                status=SolverStatus.NOT_SOLVED,
                objective_value=0.0,
                portfolio_name=portfolio_name,
                equipment_name=single_equipment.name if single_equipment else None,
            )

    def _export_optimization_results(
        self,
        output_marker,
        model: OptimisationModel,
        Portfolio: Portfolio,
        result: OptimizationResults,
    ):
        """Export optimization results using the model's variable values."""
        try:
            # Extract variable values from the solved model
            variable_values = {}
            for var_name in model.variables_name:
                variable_values[var_name] = model.get_variable_value(var_name)

            # Use output manager to export results
            # You may need to adapt this based on how OutputManager expects the data
            self.output_manager.export_results(output_marker, Portfolio, result, variable_values)

        except Exception as e:
            cfg.logger.error(f"Failed to export results: {e}")

    def _create_Portfolio(self, portfolio: Portfolio, equipment_dict: dict[EquipmentType, list]) -> Portfolio:
        """Create and initialize Portfolio object."""
        Portfolio = Portfolio(portfolio.name)

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


# Main functions for backward compatibility and ease of use
def OptimalPlacement(output_marker, parameters):
    """
    Main entry point for optimal placement optimization.

    This function maintains backward compatibility with the original interface
    while using the refactored implementation with OptimisationModel.

    Args:
        output_marker: The output marker containing all equipment data
        parameters: Optimization parameters object

    Returns:
        List of status messages from optimization
    """

    try:
        # Create optimizer and run optimization
        optimizer = OptimalPlacementOptimizer(parameters)
        status_messages = optimizer.optimize(output_marker)

        # Log final status messages
        for message in status_messages:
            cfg.logger.info(message)

        return status_messages

    except Exception as e:
        cfg.logger.error(f"Optimization failed: {str(e)}")
        raise


def OptimalPlacement_compute(
    output_marker,
    opt_portfolios,
    equipments_DT,
    equipments_DH,
    equipments_DS,
    equipments_NDL,
    equipments_DL,
    equipments_Wind,
    equipments_PV,
    equipments_NDP,
    equipment,
    parameters,
):
    """
    Legacy function for backward compatibility.

    This function is maintained for compatibility with existing code
    but internally uses the new refactored implementation with OptimisationModel.
    """
    # Convert legacy parameters to new format
    equipment_dict = {
        EquipmentType.THERMIC: equipments_DT,
        EquipmentType.HYDRAULIC: equipments_DH,
        EquipmentType.STORAGE: equipments_DS,
        EquipmentType.NON_DISPATCHABLE_LOAD: equipments_NDL,
        EquipmentType.DISPATCHABLE_LOAD: equipments_DL,
        EquipmentType.WIND: equipments_Wind,
        EquipmentType.PHOTOVOLTAIC: equipments_PV,
        EquipmentType.NON_DISPATCHABLE_PRODUCTION: equipments_NDP,
    }

    # Create optimizer
    optimizer = OptimalPlacementOptimizer(parameters)

    # Run optimization
    status_messages = optimizer._optimize_portfolio(
        output_marker, opt_portfolios, equipment_dict, single_equipment=equipment
    )

    return status_messages


# Additional utility functions
def create_default_parameters():
    """Create a parameters object with default values for testing."""
    from types import SimpleNamespace

    return SimpleNamespace(
        excluded_technologies=[],
        excluded_thermal_strategies=[],
        excluded_market_areas=[],
        is_portfolio_bidding=True,
        use_forecast=False,
        target_times=[],
        op_times=[],
        thermal_op_times=[],
        hydraulic_op_times=[],
        battery_op_times=[],
        phs_op_times=[],
        ev_op_times=[],
        time_step=60,
        solver="SCIP",  # Changed default to SCIP since it's open source
        presolve=True,
        duality_gap=0.01,
        time_out=3600,
        debug=False,
        verbose=True,
        execution_date=None,
        output_folder="./output",
        manual_unprocured_reserves_penalty=1000,
        automated_unprocured_reserves_penalty=1000,
    )


if __name__ == "__main__":
    # Example usage and testing
    print("Energy Portfolio Optimization Module with OptimisationModel")
    print("This module provides optimal placement and unit commitment functionality")
    print("using OR-Tools through the OptimisationModel interface.")

    # Create default parameters for testing
    default_params = create_default_parameters()
    print(f"Default parameters created with solver: {default_params.solver}")
