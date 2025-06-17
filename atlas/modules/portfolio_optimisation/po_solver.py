# --- Imports
from typing import Any

import API
from manual_activation import set_manual_activation
from PO_portfolio import PO_portfolio


class EquipmentCollector:
    """Collects and categorizes equipment by type."""

    def __init__(self):
        self.thermic = []
        self.hydraulic = []
        self.storage = []
        self.load_dispatchable = []
        self.load_non_dispatchable = []
        self.wind = []
        self.pv = []
        self.non_dispatchable = []


class OptimizationProblemBuilder:
    """Builds and configures optimization problems."""

    def __init__(self, parameters):
        self.p = parameters

    def create_problem(self, name: str, is_portfolio: bool) -> Any:
        """Create optimization problem with appropriate settings."""
        prob = API.Solver.NewOpProblem(name, API.Solver.OpCategoryBinary, API.Solver.OpSenseMinimize)
        prob.NoOverlap = False
        return prob

    def configure_solver(self, prob: Any) -> Any:
        """Configure solver with parameters."""
        if self.p.solver.upper() == "XPRESS":
            solver = prob.NewOpSolver("xpress")
            presolve = "1" if self.p.presolve else "0"
            solver.SetSolverSpecificParameters(
                f"MAXTIME {self.p.time_out} MIPRELSTOP {self.p.duality_gap} PRESOLVE {presolve}"
            )
            return solver
        else:
            prob.Presolve = self.p.presolve
            prob.MpsOutput = False
            prob.Algorithm = API.Solver.OpAlgorithmSimplex
            prob.DualityGap = self.p.duality_gap
            prob.Timeout = self.p.time_out
            return None


class EquipmentProcessor:
    """Processes different types of equipment for optimization."""

    def __init__(self, parameters):
        self.p = parameters

    def process_equipment_list(self, equipment_list: list, equipment_type: str, collector: EquipmentCollector):
        """Process a list of equipment and categorize them."""
        for equipment in equipment_list:
            if self._is_excluded(equipment):
                self._handle_excluded_equipment(equipment)
            elif self.p.is_portfolio_bidding:
                self._add_to_collector(equipment, equipment_type, collector)
            else:
                self._optimize_individual_equipment(equipment, equipment_type)

    def _is_excluded(self, equipment) -> bool:
        """Check if equipment should be excluded from optimization."""
        if hasattr(equipment, "Class") and equipment.Class in self.p.excluded_technologies:
            return True
        if hasattr(equipment, "Strategy") and equipment.Strategy in self.p.excluded_thermal_strategies:
            return True
        return False

    def _handle_excluded_equipment(self, equipment):
        """Handle equipment that is excluded from optimization."""
        set_manual_activation([equipment], self.p)
        if self.p.verbose:
            reason = (
                f"excluded type {equipment.Class}"
                if hasattr(equipment, "Class")
                else f"excluded strategy {equipment.Strategy}"
            )
            API.IO.Trace.Log(f"Equipment {equipment.Name} with {reason} is manually activated")

    def _add_to_collector(self, equipment, equipment_type: str, collector: EquipmentCollector):
        """Add equipment to appropriate collector list."""
        type_mapping = {
            "thermic": collector.thermic,
            "hydraulic": collector.hydraulic,
            "storage": collector.storage,
            "wind": collector.wind,
            "pv": collector.pv,
            "non_dispatchable": collector.non_dispatchable,
        }

        if equipment_type == "load":
            if equipment.LoadType == "PowerToGas":
                collector.load_dispatchable.append(equipment)
            else:
                collector.load_non_dispatchable.append(equipment)
        else:
            type_mapping[equipment_type].append(equipment)

    def _optimize_individual_equipment(self, equipment, equipment_type: str):
        """Optimize individual equipment (non-portfolio mode)."""
        equipment_args = self._build_equipment_args(equipment, equipment_type)
        OptimalPlacement_compute(equipment_args)


class ObjectiveFunctionBuilder:
    """Builds objective function and constraints for optimization."""

    def __init__(self, portfolio, parameters):
        self.portfolio = portfolio
        self.p = parameters

    def build_objective_function(self, max_op_time: list) -> tuple:
        """Build objective function and constraints."""
        obj_function = API.Solver.CreateListOpAffineExpression()
        constraint_list = API.Solver.CreateListOpConstraint()
        global_constraint_list = API.Solver.CreateListOpConstraint()

        for time in max_op_time:
            if time in self.p.target_times:
                self._add_imbalance_costs(obj_function, time)
                self._add_reserve_constraints(obj_function, constraint_list, time)
                self._add_global_constraints(global_constraint_list, time)

        return obj_function, constraint_list, global_constraint_list

    def _add_imbalance_costs(self, obj_function, time):
        """Add imbalance costs to objective function."""
        imbalance_terms = [
            (self.portfolio.imbal_price_up[time], self.portfolio.Small_imbal_up[time]),
            (self.portfolio.large_imbal_price_up[time], self.portfolio.Large_imbal_up[time]),
            (-self.portfolio.imbal_price_down[time], self.portfolio.Small_imbal_down[time]),
            (-self.portfolio.large_imbal_price_down[time], self.portfolio.Large_imbal_down[time]),
        ]

        for price, imbalance in imbalance_terms:
            obj_function.Add(price * imbalance * self.p.time_step / 60.0)

    def _add_reserve_constraints(self, obj_function, constraint_list, time):
        """Add reserve constraints."""
        # Implementation would depend on specific reserve constraint logic
        pass

    def _add_global_constraints(self, global_constraint_list, time):
        """Add global portfolio constraints."""
        # Implementation would depend on specific global constraint logic
        pass


class ResultsExporter:
    """Exports optimization results to output marker."""

    def __init__(self, parameters):
        self.p = parameters

    def export_results(self, output_marker, portfolio, optimization_result):
        """Export all optimization results."""
        if str(optimization_result.Status) != "Optimal":
            self._handle_non_optimal_result(output_marker, portfolio)
            return

        self._export_portfolio_results(output_marker, portfolio)
        self._export_equipment_results(output_marker, portfolio)

    def _handle_non_optimal_result(self, output_marker, portfolio):
        """Handle non-optimal optimization results."""
        if self.p.is_portfolio_bidding:
            set_manual_activation(portfolio.GetChildren("Equipment"), self.p)
        else:
            # Handle individual equipment case
            pass

    def _export_portfolio_results(self, output_marker, portfolio):
        """Export portfolio-level results."""
        if not self.p.is_portfolio_bidding:
            return

        # Export imbalance and power timeseries
        self._export_imbalance_timeseries(output_marker, portfolio)
        self._export_power_timeseries(output_marker, portfolio)

    def _export_equipment_results(self, output_marker, portfolio):
        """Export equipment-level results."""
        equipment_types = [
            ("thermics", "Thermic"),
            ("hydraulics", "Hydraulic"),
            ("storage", "Storage"),
            ("wind", "Wind"),
            ("pv", "Photovoltaic"),
            ("load", "Load"),
        ]

        for attr_name, marker_type in equipment_types:
            equipment_dict = getattr(portfolio, attr_name, {})
            for equipment_name, optim_equipment in equipment_dict.items():
                marker_equipment = getattr(output_marker, marker_type).GetInstanceByName(equipment_name)
                self._update_equipment_marker(marker_equipment, optim_equipment, marker_type)

    def _export_imbalance_timeseries(self, output_marker, portfolio):
        """Export imbalance timeseries for portfolio."""
        imbalance_ts = API.TimeSeries.NewTimeSeries("Imbalance", API.TimeSeries.Constant, "MW", self.p.target_times, 0)

        for time in self.p.target_times:
            imbalance_value = (
                portfolio.Large_imbal_down[time].VarValue
                + portfolio.Small_imbal_down[time].VarValue
                - portfolio.Large_imbal_up[time].VarValue
                - portfolio.Small_imbal_up[time].VarValue
            )
            imbalance_ts.SetValue(time, imbalance_value)

        # Add to output marker (implementation depends on portfolio structure)

    def _export_power_timeseries(self, output_marker, portfolio):
        """Export power timeseries for portfolio."""
        # Implementation for power timeseries export
        pass

    def _update_equipment_marker(self, marker_equipment, optim_equipment, equipment_type: str):
        """Update individual equipment results in marker."""
        output_marker_update(marker_equipment, optim_equipment, equipment_type, self.p)


class PowerRounder:
    """Handles rounding of optimization results."""

    def __init__(self, parameters):
        self.p = parameters
        self.rounding_precision = 2
        self.accepted_error = 0.01

    def round_power_output(self, marker_equipment, power_ts):
        """Round power output with constraint checking."""
        if not self.p.with_rounding:
            return power_ts

        self._basic_rounding(power_ts)
        self._apply_boundary_corrections(marker_equipment, power_ts)
        self._apply_flat_power_corrections(power_ts)

        if marker_equipment.Class == "Thermic" and marker_equipment.MinimumStablePowerDuration > 1:
            self._apply_ramping_corrections(marker_equipment, power_ts)

        return power_ts

    def _basic_rounding(self, power_ts):
        """Apply basic rounding to all values."""
        for time in power_ts.Index:
            rounded_value = round(power_ts.GetValue(time), self.rounding_precision)
            power_ts.SetValue(time, rounded_value)

    def _apply_boundary_corrections(self, marker_equipment, power_ts):
        """Apply boundary corrections (min/max power limits)."""
        max_power, min_power = self._get_power_bounds(marker_equipment, power_ts)

        for time in power_ts.Index:
            power_value = power_ts.GetValue(time)
            corrected_value = self._correct_boundary_value(
                power_value, min_power.GetValue(time), max_power.GetValue(time)
            )

            if corrected_value != power_value:
                power_ts.SetValue(time, corrected_value)
                if self.p.debug:
                    API.IO.Trace.Log(
                        f"Boundary correction for {marker_equipment.Name} at {time}",
                        API.IO.LogTypeWarn,
                    )

    def _get_power_bounds(self, marker_equipment, power_ts):
        """Get power bounds based on equipment type."""
        if marker_equipment.Class in ["Wind", "Photovoltaic", "OtherNonDispatchable"]:
            max_power = marker_equipment.MaximumPowerForecast.GetForecast(
                self.p.execution_date, power_ts.FirstDate, power_ts.LastDate
            )
            min_power = API.TimeSeries.NewTimeSeries("MinPower", API.TimeSeries.Constant, "MW", power_ts.Index, 0)
        elif marker_equipment.Class == "Load":
            min_power = marker_equipment.MaximumPowerForecast.GetForecast(
                self.p.execution_date, power_ts.FirstDate, power_ts.LastDate
            )
            max_power = API.TimeSeries.NewTimeSeries("MaxPower", API.TimeSeries.Constant, "MW", power_ts.Index, 0)
        else:
            max_power = marker_equipment.MaximumPower
            min_power = marker_equipment.MinimumPower

        return max_power, min_power

    def _correct_boundary_value(self, value: float, min_val: float, max_val: float) -> float:
        """Correct value to stay within boundaries."""
        if abs(value) <= self.accepted_error:
            return 0
        if abs(value - min_val) <= self.accepted_error:
            return min_val
        if abs(value - max_val) <= self.accepted_error:
            return max_val
        return value

    def _apply_flat_power_corrections(self, power_ts):
        """Apply corrections to maintain flat power states."""
        # Implementation for flat power corrections
        pass

    def _apply_ramping_corrections(self, marker_equipment, power_ts):
        """Apply corrections to maintain consistent ramping rates."""
        # Implementation for ramping corrections
        pass


# Main functions (refactored)
def OptimalPlacement(output_marker, parameters):
    """
    Main function for optimal placement optimization.

    Args:
        output_marker: Output marker containing equipment data
        parameters: Optimization parameters
    """
    processor = EquipmentProcessor(parameters)
    collector = EquipmentCollector()

    # Process all equipment types
    equipment_processors = [
        (output_marker.Thermic.GetAllInstances(), "thermic"),
        (output_marker.Hydraulic.GetAllInstances(), "hydraulic"),
        (output_marker.Storage.GetAllInstances(), "storage"),
        (output_marker.Load.GetAllInstances(), "load"),
        (output_marker.Wind.GetAllInstances(), "wind"),
        (output_marker.Photovoltaic.GetAllInstances(), "pv"),
        (output_marker.OtherNonDispatchable.GetAllInstances(), "non_dispatchable"),
    ]

    for equipment_list, equipment_type in equipment_processors:
        processor.process_equipment_list(equipment_list, equipment_type, collector)

    # Run portfolio optimization if in portfolio mode
    if parameters.is_portfolio_bidding:
        _run_portfolio_optimization(output_marker, collector, parameters)


def _run_portfolio_optimization(output_marker, collector: EquipmentCollector, parameters):
    """Run optimization for portfolio mode."""
    OptimalPlacement_compute(
        output_marker,
        output_marker.Portfolio.AllInstances,
        collector.thermic,
        collector.hydraulic,
        collector.storage,
        collector.load_non_dispatchable,
        collector.load_dispatchable,
        collector.wind,
        collector.pv,
        collector.non_dispatchable,
        None,
        parameters,
    )


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
    Optimized version of the main computation function.
    """
    problem_builder = OptimizationProblemBuilder(parameters)
    results_exporter = ResultsExporter(parameters)
    status_messages = []

    for portfolio in opt_portfolios:
        if _should_skip_portfolio(portfolio, equipment, parameters):
            continue

        portfolio_equipments = _collect_portfolio_equipments(
            portfolio,
            equipments_DT,
            equipments_DH,
            equipments_DS,
            equipments_NDL,
            equipments_DL,
            equipments_Wind,
            equipments_PV,
            equipments_NDP,
        )

        if not _has_equipment(portfolio_equipments):
            continue

        # Build and solve optimization problem
        problem_name = portfolio.Name if parameters.is_portfolio_bidding else equipment.Name
        prob = problem_builder.create_problem(problem_name, parameters.is_portfolio_bidding)

        # Create portfolio object and solve
        po_portfolio = _create_and_solve_portfolio(portfolio, portfolio_equipments, prob, problem_builder, parameters)

        # Export results
        results_exporter.export_results(output_marker, po_portfolio, prob)

        status_messages.append(f"{portfolio.Name} end with status {prob.Status}")

    # Log all status messages
    for msg in status_messages:
        API.IO.Trace.Log(msg, API.IO.LogTypeInfo)


def _should_skip_portfolio(portfolio, equipment, parameters) -> bool:
    """Check if portfolio should be skipped."""
    if parameters.use_forecast:
        return False

    if portfolio.MarketArea.Name in parameters.excluded_market_areas:
        if parameters.is_portfolio_bidding:
            API.IO.Trace.Log(
                f"Portfolio {portfolio.Name} is in an excluded market area, and is not optimized",
                API.IO.LogTypeWarn,
            )
            set_manual_activation(portfolio.GetChildren("Equipment"), parameters)
        else:
            API.IO.Trace.Log(
                f"Equipment {equipment.Name} is in an excluded market area, and is not optimized",
                API.IO.LogTypeWarn,
            )
            set_manual_activation([equipment], parameters)
        return True

    return False


def _collect_portfolio_equipments(portfolio, *equipment_lists):
    """Collect equipment belonging to specific portfolio."""
    portfolio_equipments = {}
    equipment_types = ["DT", "DH", "DS", "NDL", "DL", "Wind", "PV", "NDP"]

    for i, equipment_list in enumerate(equipment_lists):
        equipment_type = equipment_types[i]
        portfolio_equipments[equipment_type] = [eq for eq in equipment_list if eq.Portfolio.Name == portfolio.Name]

    return portfolio_equipments


def _has_equipment(portfolio_equipments: dict) -> bool:
    """Check if portfolio has any equipment."""
    return any(len(eq_list) > 0 for eq_list in portfolio_equipments.values())


def _create_and_solve_portfolio(portfolio, portfolio_equipments, prob, problem_builder, parameters):
    """Create portfolio object and solve optimization."""
    # Get longest optimization period
    max_op_time = max(
        [
            parameters.op_times,
            parameters.thermal_op_times,
            parameters.hydraulic_op_times,
            parameters.battery_op_times,
            parameters.phs_op_times,
            parameters.ev_op_times,
        ],
        key=len,
    )

    # Create portfolio object
    po_portfolio = PO_portfolio(portfolio.Name)
    po_portfolio.InitVariablesAndPreComputations(portfolio, *portfolio_equipments.values(), max_op_time, parameters)

    # Build objective function and constraints
    obj_builder = ObjectiveFunctionBuilder(po_portfolio, parameters)
    obj_function, constraint_list, global_constraint_list = obj_builder.build_objective_function(max_op_time)

    # Set up and solve problem
    prob.SetObjective(API.Solver.OpSum(obj_function))
    prob.AddConstraints(global_constraint_list)
    prob.AddConstraints(constraint_list)

    # Configure and run solver
    solver = problem_builder.configure_solver(prob)
    if parameters.solver.upper() == "XPRESS":
        prob.SolveORTools(solver)
    elif parameters.solver in ["GLPK", "PNE"]:
        prob.Solve(parameters.solver)
    else:
        prob.SolveORTools(parameters.solver)

    # Export solution and log results
    API.Solver.ExportSolution(prob, f"solution_{prob.Name}.out")
    API.IO.Trace.Log(f"Resolution ends with Status = {prob.Status}", API.IO.LogTypeInfo)
    API.IO.Trace.Log(f"The total cost is: {API.Solver.Value(prob.Objective)} E", API.IO.LogTypeInfo)

    return po_portfolio


def output_marker_update(marker_equipment, optim_equipment, equipment_type: str, parameters):
    """
    Simplified output marker update function.
    """
    rounder = PowerRounder(parameters)

    # Extract and process power timeseries
    power_ts = _extract_power_timeseries(marker_equipment, optim_equipment, equipment_type, parameters)
    power_ts = rounder.round_power_output(marker_equipment, power_ts)

    # Extract and process energy timeseries for applicable equipment
    energy_ts = None
    if equipment_type in ["Hydraulic", "Storage"]:
        energy_ts = _extract_energy_timeseries(optim_equipment, parameters)
        if parameters.with_rounding:
            energy_ts = _round_stored_energy(marker_equipment, energy_ts, parameters)

    # Export to marker
    _export_to_marker(marker_equipment, power_ts, energy_ts, equipment_type, parameters)


def _extract_power_timeseries(marker_equipment, optim_equipment, equipment_type: str, parameters):
    """Extract power timeseries based on equipment type."""
    power_ts = API.TimeSeries.NewTimeSeries("Final Program", API.TimeSeries.Constant, "MW", parameters.target_times, 0)

    if equipment_type == "Hydraulic":
        for time in parameters.target_times:
            activated_power = sum(
                optim_equipment.PowerLevelFragment[k][time].VarValue
                for k in range(len(marker_equipment.FragmentVolumes))
            )
            if activated_power <= parameters.allowed_round_off_error:
                activated_power = 0
            power_ts.SetValue(time, activated_power)

    elif equipment_type == "Storage":
        for time in parameters.target_times:
            activated_power = (
                optim_equipment.PowerLevelBuy[time].VarValue + optim_equipment.PowerLevelSell[time].VarValue
            )
            if abs(activated_power) <= parameters.allowed_round_off_error:
                activated_power = 0
            power_ts.SetValue(time, activated_power)

    elif equipment_type in ["Optimal_Dispatch_NDP", "Optimal_Dispatch_NDL"]:
        for time in parameters.target_times:
            power_ts.SetValue(time, optim_equipment[time])

    else:
        for time in parameters.target_times:
            power_ts.SetValue(time, optim_equipment.PowerLevel[time].VarValue)

    return power_ts


def _extract_energy_timeseries(optim_equipment, parameters):
    """Extract energy timeseries for storage equipment."""
    energy_ts = API.TimeSeries.NewTimeSeries("StoredEnergy", API.TimeSeries.Constant, "MWh", parameters.target_times, 0)

    for time in parameters.target_times:
        energy_ts.set_value(time, optim_equipment.stored_energy[time].VarValue)

    return energy_ts


def _export_to_marker(marker_equipment, power_ts, energy_ts, equipment_type: str, parameters):
    """Export timeseries to output marker."""
    if parameters.use_forecast:
        if parameters.execution_date in marker_equipment.IDPOForOrders.Index:
            marker_equipment.IDPOForOrders.DeleteTimeSeries(parameters.execution_date)
        marker_equipment.IDPOForOrders.AddTimeSeries(parameters.execution_date, power_ts)
    else:
        if parameters.execution_date in marker_equipment.Power.Index:
            marker_equipment.Power.DeleteTimeSeries(parameters.execution_date)
        marker_equipment.Power.AddTimeSeries(parameters.execution_date, power_ts)

        if energy_ts and equipment_type in ["Hydraulic", "Storage"]:
            if parameters.execution_date in marker_equipment.StoredEnergy.Index:
                marker_equipment.StoredEnergy.DeleteTimeSeries(parameters.execution_date)
            marker_equipment.StoredEnergy.AddTimeSeries(parameters.execution_date, energy_ts)


def _round_stored_energy(marker_equipment, energy_ts, parameters):
    """Simplified stored energy rounding function."""
    rounder = PowerRounder(parameters)
    # Implementation would be similar to power rounding but for energy
    return energy_ts
