import atlas.config as cfg
from atlas.enum import SolverStatus
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.main import OptimizationResults
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


class OutputManager:
    """Manages optimization output and result export."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def export_results(self, output_marker, portfolio: Portfolio, optimization_results: OptimizationResults):
        """Export optimization results to the output marker."""
        if optimization_results.status != SolverStatus.OPTIMAL:
            cfg.logger.warning(f"Optimization for {portfolio.name} failed with status: {optimization_results.status}")
            return

        self._export_portfolio_results(output_marker, portfolio)
        self._export_equipment_results(output_marker, portfolio)

    def _export_portfolio_results(self, output_marker, portfolio: Portfolio):
        """Export portfolio-level results."""
        if not self.parameters.is_portfolio_bidding:
            return

        # Export imbalance time series
        self._export_imbalance_timeseries(output_marker, portfolio)

        # Export total power time series
        self._export_power_timeseries(output_marker, portfolio)

    def _export_imbalance_timeseries(self, output_marker, portfolio: Portfolio):
        """Export portfolio imbalance time series."""
        imbalance_ts = API.TimeSeries.NewTimeSeries(
            "Imbalance", API.TimeSeries.Constant, "MW", self.parameters.target_times, 0
        )

        for time in self.parameters.target_times:
            imbalance_value = (
                portfolio.large_imbalance_down[time].VarValue
                + portfolio.small_imbalance_down[time].VarValue
                - portfolio.large_imbalance_up[time].VarValue
                - portfolio.small_imbalance_up[time].VarValue
            )
            imbalance_ts.SetValue(time, imbalance_value)

        # Find portfolio in output marker and add time series
        opt_portfolio = self._find_portfolio_by_name(output_marker, portfolio.name)
        if opt_portfolio:
            opt_portfolio.Imbalance.add(self.parameters.execution_date, imbalance_ts)

    def _export_power_timeseries(self, output_marker, portfolio: Portfolio):
        """Export portfolio total power time series."""
        power_ts = API.TimeSeries.NewTimeSeries(
            "PO_power", API.TimeSeries.Constant, "MW", self.parameters.target_times, 0
        )

        opt_portfolio = self._find_portfolio_by_name(output_marker, portfolio.name)
        if not opt_portfolio:
            return

        equipment_list = opt_portfolio.GetChildren("Equipment")

        for time in self.parameters.target_times:
            total_power = 0
            for marker_equipment in equipment_list:
                forecast = marker_equipment.power.get_forecast(self.parameters.execution_date, time, time)
                total_power += forecast.GetValue(time)

            power_ts.SetValue(time, total_power)

        # Replace existing power time series
        if self.parameters.execution_date in opt_portfolio.power.index:
            opt_portfolio.power.delete(self.parameters.execution_date)
        opt_portfolio.power.add(self.parameters.execution_date, power_ts)

    def _export_equipment_results(self, output_marker, portfolio: Portfolio):
        """Export individual equipment results."""
        equipment_exporters = {
            "thermics": ("Thermic", output_marker.Thermic),
            "hydraulics": ("Hydraulic", output_marker.Hydraulic),
            "storage": ("Storage", output_marker.Storage),
            "wind": ("Wind", output_marker.Wind),
            "pv": ("Photovoltaic", output_marker.Photovoltaic),
            "load": ("Load", output_marker.Load),
        }

        for attr_name, (equipment_type, marker_collection) in equipment_exporters.items():
            equipment_dict = getattr(portfolio, attr_name, {})
            for equipment_name, optim_equipment in equipment_dict.items():
                marker_equipment = marker_collection.GetInstanceByName(equipment_name)
                if marker_equipment:
                    self._update_output_marker(marker_equipment, optim_equipment, equipment_type)

        # Export non-dispatchable results
        self._export_non_dispatchable_results(output_marker, portfolio)

    def _export_non_dispatchable_results(self, output_marker, portfolio: Portfolio):
        """Export non-dispatchable equipment results."""
        # Non-dispatchable load
        for equipment_name, dispatch_values in portfolio.Optimal_dispatch_NDL.items():
            marker_equipment = output_marker.Load.GetInstanceByName(equipment_name)
            if marker_equipment:
                self._update_output_marker(marker_equipment, dispatch_values, "Optimal_Dispatch_NDL")

        # Non-dispatchable production
        for equipment_name, dispatch_values in portfolio.Optimal_dispatch_NDP.items():
            marker_equipment = output_marker.OtherNonDispatchable.GetInstanceByName(equipment_name)
            if marker_equipment:
                self._update_output_marker(marker_equipment, dispatch_values, "Optimal_Dispatch_NDP")

    def _find_portfolio_by_name(self, output_marker, portfolio_name: str):
        """Find portfolio in output marker by name."""
        for portfolio in output_marker.Portfolio.AllInstances:
            if portfolio.Name == portfolio_name:
                return portfolio
        return None

    def _update_output_marker(self, marker_equipment, optim_equipment, equipment_type: str):
        """Update output marker with optimization results."""
        # This method would contain the logic from the original output_marker_update function
        # Implementation depends on the specific output_marker_update function
        pass
