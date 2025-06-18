"""
Energy Portfolio Optimization Module

This module provides optimal placement and unit commitment functionality for
energy portfolios containing various types of generation, storage, and load equipment.
"""

import logging
import os
from dataclasses import dataclass

# Third-party imports
import API

import atlas.config as cfg

# Local imports
from atlas.modules.portfolio_optimisation import PO_portfolio
from atlas.modules.portfolio_optimisation.enum import EquipmentType, SolverStatus
from atlas.modules.portfolio_optimisation.utils import set_manual_activation
from atlas.modules.portfolio_optimisation.utils.constraint_builder import ConstraintBuilder
from atlas.modules.portfolio_optimisation.utils.equipment import (
    EquipmentClassifier,
    EquipmentCollector,
)
from atlas.modules.portfolio_optimisation.utils.output_manager import OutputManager


@dataclass
class OptimizationResults:
    """Results from the optimization process."""

    status: SolverStatus
    objective_value: float
    portfolio_name: str
    equipment_name: str | None = None
    solve_time: float | None = None
    gap: float | None = None


class ObjectiveFunctionBuilder:
    """Builds the optimization objective function."""

    def __init__(self, parameters):
        self.parameters = parameters

    def build_objective(self, portfolio: PO_portfolio, target_times: list) -> list:
        """Build the complete objective function."""
        obj_function = API.Solver.CreateListOpAffineExpression()

        for time in target_times:
            self._add_imbalance_costs(obj_function, portfolio, time)
            self._add_reserve_penalties(obj_function, portfolio, time)

        return obj_function

    def _add_imbalance_costs(self, obj_function: list, portfolio: PO_portfolio, time):
        """Add imbalance cost terms to objective function."""
        time_factor = self.parameters.time_step / 60.0

        # Small imbalance costs
        obj_function.Add(portfolio.imbal_price_up[time] * portfolio.Small_imbal_up[time] * time_factor)
        obj_function.Add(-portfolio.imbal_price_down[time] * portfolio.Small_imbal_down[time] * time_factor)

        # Large imbalance costs
        obj_function.Add(portfolio.large_imbal_price_up[time] * portfolio.Large_imbal_up[time] * time_factor)
        obj_function.Add(-portfolio.large_imbal_price_down[time] * portfolio.Large_imbal_down[time] * time_factor)

    def _add_reserve_penalties(self, obj_function: list, portfolio: PO_portfolio, time):
        """Add reserve penalty terms to objective function."""
        time_factor = self.parameters.time_step / 60.0

        # Manual reserve penalties
        obj_function.Add(
            self.parameters.manual_unprocured_reserves_penalty * time_factor * portfolio.contractedDifferenceUp[time]
        )
        obj_function.Add(
            self.parameters.manual_unprocured_reserves_penalty * time_factor * portfolio.contractedDifferenceDown[time]
        )

        # Automated reserve penalties
        obj_function.Add(
            self.parameters.automated_unprocured_reserves_penalty
            * time_factor
            * portfolio.automatedContractedDifferenceUp[time]
        )
        obj_function.Add(
            self.parameters.automated_unprocured_reserves_penalty
            * time_factor
            * portfolio.automatedContractedDifferenceDown[time]
        )


class OptimalPlacementOptimizer:
    """Main class for optimal placement optimization."""

    def __init__(self, parameters):
        self.parameters = parameters

        # Initialize components
        self.equipment_classifier = EquipmentClassifier(parameters)
        self.equipment_collector = EquipmentCollector()
        self.solver_manager = OptimisationModel(parameters)
        self.objective_builder = ObjectiveFunctionBuilder(parameters)
        self.constraint_builder = ConstraintBuilder(parameters)
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

        # Collect other equipment types (hydraulic, storage, load, wind, pv, non-dispatchable)
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
        # Individual equipment optimization is handled during collection
        return []

    def _optimize_single_equipment(self, output_marker, equipment, equipment_type: EquipmentType):
        """Optimize a single equipment unit."""
        equipment_dict = {et: [] for et in EquipmentType}
        equipment_dict[equipment_type] = [equipment]

        self._optimize_portfolio(output_marker, [equipment.Portfolio], equipment_dict, single_equipment=equipment)

    def _optimize_portfolio(
        self,
        output_marker,
        portfolios: list,
        equipment_dict: dict[EquipmentType, list],
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
            portfolio_equipment = self._filter_equipment_by_portfolio(equipment_dict, portfolio.Name)

            # Skip if no equipment
            if not any(equipment_list for equipment_list in portfolio_equipment.values()):
                continue

            # Perform optimization
            result = self._optimize_single_portfolio(output_marker, portfolio, portfolio_equipment, single_equipment)

            status_messages.append(f"{portfolio.Name} ended with status {result.status.value}")

        return status_messages

    def _optimize_single_portfolio(
        self,
        output_marker,
        portfolio,
        equipment_dict: dict[EquipmentType, list],
        single_equipment=None,
    ) -> OptimizationResults:
        """Optimize a single portfolio."""
        portfolio_name = single_equipment.Name if single_equipment else portfolio.Name

        cfg.logger.info(f"Optimizing portfolio: {portfolio_name}")

        # Create optimization problem
        problem = self.solver_manager.create_optimization_problem(portfolio_name)

        # Create portfolio object
        po_portfolio = self._create_po_portfolio(portfolio, equipment_dict)

        # Build objective function and constraints
        obj_function = self.objective_builder.build_objective(po_portfolio, self.parameters.target_times)

        optimization_times = self._get_optimization_times()
        constraint_list, global_constraint_list = self.constraint_builder.build_constraints(
            po_portfolio, optimization_times
        )

        # Set up problem
        problem.NoOverlap = False
        problem.SetObjective(API.Solver.OpSum(obj_function))
        problem.AddConstraints(global_constraint_list)
        problem.AddConstraints(constraint_list)

        # Debug output
        if self.parameters.debug:
            self._write_debug_output(problem, portfolio_name, single_equipment)

        # Solve problem
        result = self.solver_manager.solve_problem(problem)

        cfg.logger.info(f"Portfolio {portfolio_name} optimization completed with status: {result.status.value}")

        # Export results
        if result.status == SolverStatus.OPTIMAL:
            self.output_manager.export_results(output_marker, po_portfolio, result)
        else:
            # Fallback to manual activation
            equipment_list = [single_equipment] if single_equipment else portfolio.GetChildren("Equipment")
            set_manual_activation(equipment_list, self.parameters)

        return result

    def _create_po_portfolio(self, portfolio, equipment_dict: dict[EquipmentType, list]) -> PO_portfolio:
        """Create and initialize PO_portfolio object."""
        po_portfolio = PO_portfolio(portfolio.Name)

        # Get longest optimization period
        optimization_times = self._get_optimization_times()
        max_op_time = max(optimization_times.values(), key=len)

        # Initialize portfolio
        po_portfolio.InitVariablesAndPreComputations(
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

        return po_portfolio

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
        self, equipment_dict: dict[EquipmentType, list], portfolio_name: str
    ) -> dict[EquipmentType, list]:
        """Filter equipment dictionary to only include equipment from specified portfolio."""
        filtered_dict = {equipment_type: [] for equipment_type in EquipmentType}

        for equipment_type, equipment_list in equipment_dict.items():
            for equipment in equipment_list:
                if equipment.Portfolio.Name == portfolio_name:
                    filtered_dict[equipment_type].append(equipment)

        return filtered_dict

    def _handle_excluded_market_area(self, portfolio, single_equipment=None):
        """Handle portfolios in excluded market areas."""
        if self.parameters.is_portfolio_bidding:
            cfg.logger.warning(f"Portfolio {portfolio.Name} is in excluded market area and will not be optimized")
            set_manual_activation(portfolio.GetChildren("Equipment"), self.parameters)
        else:
            cfg.logger.warning(
                f"Equipment {single_equipment.Name} is in excluded market area and will not be optimized"
            )
            set_manual_activation([single_equipment], self.parameters)

    def _write_debug_output(self, problem, portfolio_name: str, single_equipment=None):
        """Write debug output files."""
        if single_equipment:
            lp_file_name = os.path.join(self.parameters.output_folder, f"Equipment_{single_equipment.Name}.lp")
        else:
            lp_file_name = os.path.join(self.parameters.output_folder, f"Portfolio_{portfolio_name}.lp")

        if self.parameters.solver.upper() == "XPRESS":
            problem.WriteLP(lp_file_name, True)
        else:
            problem.WriteLP(lp_file_name)
            # Print LP content for debugging
            try:
                with open(os.path.join(API.Workspace, lp_file_name)) as f:
                    print(f.read())
            except FileNotFoundError:
                cfg.logger.warning(f"Could not read LP file: {lp_file_name}")


class ValidationHelper:
    """Helper class for input validation and error checking."""

    @staticmethod
    def validate_parameters(parameters) -> list[str]:
        """Validate optimization parameters."""
        errors = []

        # Check required attributes
        required_attrs = [
            "excluded_technologies",
            "excluded_thermal_strategies",
            "excluded_market_areas",
            "is_portfolio_bidding",
            "use_forecast",
            "target_times",
            "op_times",
            "thermal_op_times",
            "hydraulic_op_times",
            "battery_op_times",
            "phs_op_times",
            "ev_op_times",
            "time_step",
            "solver",
            "presolve",
            "duality_gap",
            "time_out",
            "debug",
            "verbose",
            "execution_date",
            "output_folder",
        ]

        for attr in required_attrs:
            if not hasattr(parameters, attr):
                errors.append(f"Missing required parameter: {attr}")

        # Validate solver
        if hasattr(parameters, "solver"):
            valid_solvers = ["GLPK", "PNE", "XPRESS", "CPLEX", "GUROBI"]
            if parameters.solver.upper() not in valid_solvers:
                errors.append(f"Invalid solver: {parameters.solver}")

        # Validate time parameters
        if hasattr(parameters, "time_step") and parameters.time_step <= 0:
            errors.append("time_step must be positive")

        if hasattr(parameters, "time_out") and parameters.time_out <= 0:
            errors.append("time_out must be positive")

        if hasattr(parameters, "duality_gap") and not (0 <= parameters.duality_gap <= 1):
            errors.append("duality_gap must be between 0 and 1")

        return errors

    @staticmethod
    def validate_output_marker(output_marker) -> list[str]:
        """Validate output marker structure."""
        errors = []

        required_collections = [
            "Thermic",
            "Hydraulic",
            "Storage",
            "Load",
            "Wind",
            "Photovoltaic",
            "OtherNonDispatchable",
            "Portfolio",
        ]

        for collection in required_collections:
            if not hasattr(output_marker, collection):
                errors.append(f"Missing collection in output_marker: {collection}")

        return errors


# Main functions for backward compatibility and ease of use
def OptimalPlacement(output_marker, parameters):
    """
    Main entry point for optimal placement optimization.

    This function maintains backward compatibility with the original interface
    while using the refactored, cleaner implementation.

    Args:
        output_marker: The output marker containing all equipment data
        parameters: Optimization parameters object

    Returns:
        List of status messages from optimization
    """
    # Validate inputs
    param_errors = ValidationHelper.validate_parameters(parameters)
    if param_errors:
        raise ValueError(f"Parameter validation failed: {param_errors}")

    marker_errors = ValidationHelper.validate_output_marker(output_marker)
    if marker_errors:
        raise ValueError(f"Output marker validation failed: {marker_errors}")

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if parameters.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        # Create optimizer and run optimization
        optimizer = OptimalPlacementOptimizer(parameters)
        status_messages = optimizer.optimize(output_marker)

        # Log final status messages
        logger = logging.getLogger(__name__)
        for message in status_messages:
            logger.info(message)

        return status_messages

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Optimization failed: {str(e)}")
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
    but internally uses the new refactored implementation.
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
        solver="CPLEX",
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


def output_marker_update(marker_equipment, optim_equipment, equipment_type: str, parameters):
    """
    Update output marker with optimization results.

    This function should be implemented based on the specific requirements
    of your system for updating the output marker with optimization results.

    Args:
        marker_equipment: Equipment object in the output marker
        optim_equipment: Optimized equipment results
        equipment_type: Type of equipment being updated
        parameters: Optimization parameters
    """
    # Placeholder implementation - should be replaced with actual logic
    # based on your system's requirements

    logger = logging.getLogger(__name__)
    logger.info(f"Updating {equipment_type} equipment: {marker_equipment.Name}")

    # Example implementation structure:
    # - Update power output time series
    # - Update reserve procurement results
    # - Update operational status
    # - Update cost/revenue calculations

    pass


if __name__ == "__main__":
    # Example usage and testing
    print("Energy Portfolio Optimization Module")
    print("This module provides optimal placement and unit commitment functionality")
    print("for energy portfolios containing various types of generation, storage, and load equipment.")

    # Create default parameters for testing
    default_params = create_default_parameters()
    print(f"Default parameters created with solver: {default_params.solver}")

    # Validate default parameters
    validation_errors = ValidationHelper.validate_parameters(default_params)
    if validation_errors:
        print(f"Validation errors found: {validation_errors}")
    else:
        print("Default parameters validation passed")
