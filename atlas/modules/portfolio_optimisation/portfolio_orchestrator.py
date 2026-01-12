"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from pendulum import DateTime

import atlas.config as cfg
from atlas.enum import SolverStatus
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.models.portfolio_equipments import PortfolioEquipments
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.portfolio_optimisation_model import PortfolioOptimisationModel
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.solver.models import SolutionInfo, SolverOptions


@dataclass
class PortfolioOptimisationResult:
    """
    This class stores the optimization results without the unpicklable solver object,
    making it suitable for multiprocessing with ProcessPoolExecutor.

    Attributes:
        portfolio: The optimized portfolio object
        parameters: Optimization parameters used
        variable_values: Dictionary mapping variable names to their optimized values
        solution_info: Dictionary containing solver status, objective value, and solve time
    """

    portfolio: PortfolioPO
    solution_info: SolutionInfo | None
    variable_values: dict[str, float] = field(default_factory=dict)

    def get_variable_value(self, var_name: str) -> float:
        """
        Get the value of an optimization variable by name.

        This method provides the same interface as PortfolioOptimisationModel.get_variable_value(),
        allowing transparent usage in the output dataset.

        Args:
            var_name: Name of the variable

        Returns:
            The variable's optimized value, or 0.0 if the variable doesn't exist
        """
        return self.variable_values.get(var_name, 0.0)

    @property
    def name(self) -> str:
        """Get the portfolio name (for compatibility with model interface)."""
        return self.portfolio.name

    def __repr__(self) -> str:
        return f"PortfolioOptimisationResult(portfolio={self.portfolio.name}, optimisation_status={self.solution_info.status})"


def optimise_single_portfolio(
    portfolio: PortfolioPO, time_window: list[DateTime], parameters: PortfolioOptimisationParameters
) -> tuple[str, PortfolioOptimisationResult]:
    """
    Worker function for portfolio optimization (works for both multiprocessing and sequential).

    Builds and solves the optimization model, then extracts results into a picklable
    PortfolioOptimisationResult object (avoiding SWIG solver objects).

    Args:
        portfolio: Portfolio to optimize
        time_window: Time window for optimization
        parameters: Optimization parameters

    Returns:
        Tuple of (portfolio_name, optimization_result)
    """
    solver_options = SolverOptions(
        presolve=parameters.use_presolve,
        duality_gap=parameters.solver_duality_gap,
        time_limit=parameters.solver_timeout,
    )
    model = PortfolioOptimisationModel(portfolio, parameters, solver_options=solver_options)

    try:
        model.set_direction("minimize")
        model.build(time_window)

        if parameters.export_lp:
            lp_dir = Path(parameters.export_lp_path)
            lp_dir.mkdir(parents=True, exist_ok=True)
            model.export_model(str(lp_dir / f"po_{portfolio.name}.lp"))

        model.solve()

        variable_values = {var_name: model.get_variable_value(var_name) for var_name in model._variables_name}

        result = PortfolioOptimisationResult(
            portfolio=model.portfolio, variable_values=variable_values, solution_info=model.solution_info
        )

        return portfolio.name, result

    except Exception as e:
        cfg.logger.error(f"Optimisation failed for portfolio {portfolio.name}: {e}")
        cfg.logger.debug("Falling back to manual activation")

        set_manual_activation(portfolio.equipments.get_all_equipment(), parameters)

        result = PortfolioOptimisationResult(
            portfolio=portfolio, variable_values={}, solution_info=SolutionInfo(status=SolverStatus.NOT_SOLVED)
        )

        return portfolio.name, result


class PortfolioOptimisationOrchestrator:
    """Orchestrates optimization across multiple portfolios."""

    def __init__(self, parameters: PortfolioOptimisationParameters):
        self.parameters = parameters

    def run(self, input_dataset: PortfolioOptimisationInputDataset) -> dict[str, PortfolioOptimisationResult]:
        """
        Main optimisation method with multiprocessing or sequential support.

        Uses ProcessPoolExecutor to parallelize portfolio optimization if use_multiprocessing is True,
        otherwise uses a simple for loop. Results are returned as PortfolioOptimisationResult objects
        (picklable) instead of models with SWIG objects.
        """
        cfg.logger.info(
            "Starting Portfolio Optimisation\n"
            f"  Start Date:          {self.parameters.start_date}\n"
            f"  End Date:            {self.parameters.end_date}\n"
            f"  Execution Date:      {self.parameters.execution_date}\n"
            f"  Portfolios:          {len(input_dataset.portfolios)}\n"
            f"  Manual Activation:   {len(input_dataset.portfolios_manual_activation)}\n"
            f"  Mode:                {'Portfolio Bidding' if self.parameters.is_portfolio_bidding else 'Individual Equipment'}\n"
        )
        optimisation_results: dict[str, PortfolioOptimisationResult] = {}

        if self.parameters.is_portfolio_bidding:
            if self.parameters.use_multiprocessing:
                optimisation_results = self._run_portfolio_multiprocessing(input_dataset)
            else:
                optimisation_results = self._run_portfolio_sequential(input_dataset)

            for portfolio in input_dataset.portfolios_manual_activation:
                optimisation_results[portfolio.name] = self._optimise_portfolio_manual_activated(portfolio=portfolio)
        else:
            cfg.logger.debug("Individual equipment optimisation mode")

            if self.parameters.use_multiprocessing:
                optimisation_results = self._run_equipment_multiprocessing(input_dataset)
            else:
                optimisation_results = self._run_equipment_sequential(input_dataset)

            for portfolio_manual in input_dataset.portfolios_manual_activation:
                for equipment_type, list_equipment in portfolio_manual.equipments.iter_by_type():
                    for equipment in list_equipment:
                        # Create a single-equipment portfolio
                        single_equipment = PortfolioEquipments()
                        single_equipment.add(equipment_type, equipment)

                        equipment_portfolio = PortfolioPO(
                            name=equipment.name,
                            equipments=single_equipment,
                            control_block=portfolio_manual.control_block,
                            market_area=portfolio_manual.market_area,
                        )

                        optimisation_results[equipment_portfolio.name] = self._optimise_portfolio_manual_activated(
                            portfolio=equipment_portfolio
                        )

        return optimisation_results

    def _run_portfolio_multiprocessing(
        self, input_dataset: PortfolioOptimisationInputDataset
    ) -> dict[str, PortfolioOptimisationResult]:
        """Run portfolio optimization using multiprocessing."""
        optimisation_results: dict[str, PortfolioOptimisationResult] = {}

        with ProcessPoolExecutor(max_workers=self.parameters.max_workers) as executor:
            # Submit all portfolio optimization tasks
            future_to_portfolio = {
                executor.submit(
                    optimise_single_portfolio,
                    portfolio,
                    input_dataset.time_windows[portfolio.name],
                    self.parameters,
                ): portfolio.name
                for portfolio in input_dataset.portfolios
            }

            # Collect results as they complete
            for future in as_completed(future_to_portfolio):
                portfolio_name = future_to_portfolio[future]
                try:
                    name, result = future.result()
                    optimisation_results[name] = result
                    cfg.logger.info(f"Completed optimization for portfolio: {name}")
                except Exception as e:
                    cfg.logger.error(f"Error processing portfolio {portfolio_name}: {e}")

        return optimisation_results

    def _run_portfolio_sequential(
        self, input_dataset: PortfolioOptimisationInputDataset
    ) -> dict[str, PortfolioOptimisationResult]:
        """Run portfolio optimization sequentially using a for loop."""
        optimisation_results: dict[str, PortfolioOptimisationResult] = {}

        for portfolio in input_dataset.portfolios:
            try:
                name, result = optimise_single_portfolio(
                    portfolio, input_dataset.time_windows[portfolio.name], self.parameters
                )
                optimisation_results[name] = result
                cfg.logger.info(f"Completed optimization for portfolio: {name}")
            except Exception as e:
                cfg.logger.error(f"Error processing portfolio {portfolio.name}: {e}")

        return optimisation_results

    def _run_equipment_multiprocessing(
        self, input_dataset: PortfolioOptimisationInputDataset
    ) -> dict[str, PortfolioOptimisationResult]:
        """Run equipment optimization using multiprocessing."""
        optimisation_results: dict[str, PortfolioOptimisationResult] = {}
        equipment_portfolios: list[tuple[PortfolioPO, list[DateTime], str]] = []

        for portfolio in input_dataset.portfolios:
            cfg.logger.debug(f"Processing portfolio {portfolio.name} for individual equipment optimisation")
            for equipment_type, list_equipment in portfolio.equipments.iter_by_type():
                for equipment in list_equipment:
                    single_equipment = PortfolioEquipments()
                    setattr(single_equipment, equipment_type, [equipment])

                    equipment_portfolio = PortfolioPO(
                        name=equipment.name,
                        equipments=single_equipment,
                        control_block=portfolio.control_block,
                        market_area=portfolio.market_area,
                    )

                    equipment_portfolio.market_area.set_market_context(
                        self.parameters.market, self.parameters.use_forecast
                    )

                    equipment_portfolios.append(
                        (equipment_portfolio, input_dataset.time_windows[portfolio.name], portfolio.name)
                    )

        with ProcessPoolExecutor(max_workers=self.parameters.max_workers) as executor:
            future_to_equipment = {
                executor.submit(optimise_single_portfolio, eq_portfolio, time_window, self.parameters): (
                    eq_portfolio.name,
                    original_name,
                )
                for eq_portfolio, time_window, original_name in equipment_portfolios
            }

            for future in as_completed(future_to_equipment):
                equipment_name, original_portfolio_name = future_to_equipment[future]
                try:
                    name, result = future.result()
                    optimisation_results[original_portfolio_name] = result
                    cfg.logger.info(f"Completed optimization for equipment: {name}")
                except Exception as e:
                    cfg.logger.error(f"Error processing equipment {equipment_name}: {e}")

        return optimisation_results

    def _run_equipment_sequential(
        self, input_dataset: PortfolioOptimisationInputDataset
    ) -> dict[str, PortfolioOptimisationResult]:
        """Run equipment optimization sequentially using a for loop."""
        optimisation_results: dict[str, PortfolioOptimisationResult] = {}

        for portfolio in input_dataset.portfolios:
            cfg.logger.debug(f"Processing portfolio {portfolio.name} for individual equipment optimisation")
            for equipment_type, list_equipment in portfolio.equipments.iter_by_type():
                for equipment in list_equipment:
                    single_equipment = PortfolioEquipments()
                    setattr(single_equipment, equipment_type, [equipment])

                    equipment_portfolio = PortfolioPO(
                        name=equipment.name,
                        equipments=single_equipment,
                        control_block=portfolio.control_block,
                        market_area=portfolio.market_area,
                    )

                    equipment_portfolio.market_area.set_market_context(
                        self.parameters.market, self.parameters.use_forecast
                    )

                    try:
                        name, result = optimise_single_portfolio(
                            equipment_portfolio, input_dataset.time_windows[portfolio.name], self.parameters
                        )
                        optimisation_results[portfolio.name] = result
                        cfg.logger.info(f"Completed optimization for equipment: {name}")
                    except Exception as e:
                        cfg.logger.error(f"Error processing equipment {equipment.name}: {e}")

        return optimisation_results

    def _optimise_portfolio_manual_activated(self, portfolio: PortfolioPO) -> PortfolioOptimisationResult:
        """
        Create a result object for manually activated portfolios.

        Args:
            portfolio: Portfolio to manually activate

        Returns:
            PortfolioOptimisationResult with manual activation applied
        """
        cfg.logger.info(f"Manual activation for portfolio: {portfolio.name}")
        cfg.logger.debug("Manual activation optimisation not yet implemented")

        set_manual_activation(portfolio.equipments.get_all_equipment(), self.parameters)

        return PortfolioOptimisationResult(
            portfolio=portfolio, variable_values={}, solution_info=SolutionInfo(status=SolverStatus.NOT_SOLVED)
        )
