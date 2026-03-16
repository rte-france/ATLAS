"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import SolverStatus
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

    :param portfolio: The optimized portfolio object
    :type portfolio: PortfolioPO
    :param solution_info: Dictionary containing solver status, objective value, and solve time
    :type solution_info: SolutionInfo | None
    :param variable_values: Dictionary mapping variable names to their optimized values
    :type variable_values: dict[str, float]
    """

    portfolio: PortfolioPO
    solution_info: SolutionInfo | None
    variable_values: dict[str, float] = field(default_factory=dict)

    def get_variable_value(self, var_name: str) -> float:
        """
        Get the value of an optimization variable by name.

        This method provides the same interface as PortfolioOptimisationModel.get_variable_value(),
        allowing transparent usage in the output dataset.

        :param var_name: Name of the variable
        :type var_name: str
        :return: The variable's optimized value, or 0.0 if the variable doesn't exist
        :rtype: float
        """
        return self.variable_values.get(var_name, 0.0)

    @property
    def name(self) -> str:
        """Get the portfolio name (for compatibility with model interface)."""
        return self.portfolio.name

    def __repr__(self) -> str:
        return f"PortfolioOptimisationResult(portfolio={self.portfolio.name}"


def optimise_single_portfolio(
    portfolio: PortfolioPO, time_window: list[DateTime], parameters: PortfolioOptimisationParameters
) -> tuple[str, PortfolioOptimisationResult]:
    """
    Worker function for portfolio optimization (works for both multiprocessing and sequential).

    Builds and solves the optimization model, then extracts results into a picklable
    PortfolioOptimisationResult object (avoiding SWIG solver objects).

    :param portfolio: Portfolio to optimize
    :type portfolio: PortfolioPO
    :param time_window: Time window for optimization
    :type time_window: list[DateTime]
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Tuple of (portfolio_name, optimization_result)
    :rtype: tuple[str, PortfolioOptimisationResult]
    """
    solver_options = SolverOptions(
        presolve=parameters.solver.use_presolve,
        duality_gap=parameters.solver.duality_gap,
        time_limit=parameters.solver.timeout,
    )
    model = PortfolioOptimisationModel(portfolio, parameters, solver_options=solver_options)

    try:
        model.set_direction("minimize")
        model.build(time_window)

        if parameters.solver.export_lp:
            output_path = parameters.get_output_dir() / "lp_export"
            output_path.mkdir(parents=True, exist_ok=True)
            model.export_model(output_path  / f"po_{portfolio.name}.lp")

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
            f"  Start Date:          {self.parameters.date.start_date}\n"
            f"  End Date:            {self.parameters.date.end_date}\n"
            f"  Execution Date:      {self.parameters.date.execution_date}\n"
            f"  Portfolios:          {len(input_dataset.portfolios)}\n"
            f"  Manual Activation:   {len(input_dataset.portfolios_manual_activation)}\n"
            f"  Mode:                {'Portfolio Bidding' if self.parameters.is_portfolio_bidding else 'Individual Equipment'}\n"
        )
        optimisation_results: dict[str, PortfolioOptimisationResult] = {}

        # Prepare portfolios based on bidding mode
        if self.parameters.is_portfolio_bidding:
            portfolios_with_time_windows = [
                (portfolio, input_dataset.time_windows[portfolio.name]) for portfolio in input_dataset.portfolios
            ]
        else:
            portfolios_with_time_windows = self._prepare_equipment_portfolios(input_dataset)

        if self.parameters.multiprocessing.use_multiprocessing:
            optimisation_results = self._run_multiprocessing(portfolios_with_time_windows)
        else:
            optimisation_results = self._run_sequential(portfolios_with_time_windows)

        # Handle manual activation portfolios
        if self.parameters.is_portfolio_bidding:
            for portfolio in input_dataset.portfolios_manual_activation:
                optimisation_results[portfolio.name] = self._optimise_portfolio_manual_activated(portfolio=portfolio)
        else:
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

    def _prepare_equipment_portfolios(
        self, input_dataset: PortfolioOptimisationInputDataset
    ) -> list[tuple[PortfolioPO, list[DateTime]]]:
        """
        Prepare individual equipment portfolios from the input portfolios.

        :param input_dataset: Input dataset containing portfolios
        :type input_dataset: PortfolioOptimisationInputDataset
        :return: List of tuples containing equipment portfolios and their time windows
        :rtype: list[tuple[PortfolioPO, list[DateTime]]]
        """
        equipment_portfolios: list[tuple[PortfolioPO, list[DateTime]]] = []

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

                    equipment_portfolios.append((equipment_portfolio, input_dataset.time_windows[portfolio.name]))

        return equipment_portfolios

    def _run_multiprocessing(
        self, portfolios_with_time_windows: list[tuple[PortfolioPO, list[DateTime]]]
    ) -> dict[str, PortfolioOptimisationResult]:
        """
        Generic method to run optimization using multiprocessing.

        :param portfolios_with_time_windows: List of tuples containing portfolios and their time windows
        :type portfolios_with_time_windows: list[tuple[PortfolioPO, list[DateTime]]]
        :return: Dictionary mapping portfolio names to optimization results
        :rtype: dict[str, PortfolioOptimisationResult]
        """
        optimisation_results: dict[str, PortfolioOptimisationResult] = {}

        with ProcessPoolExecutor(max_workers=self.parameters.multiprocessing.max_workers) as executor:
            future_to_portfolio = {
                executor.submit(optimise_single_portfolio, portfolio, time_window, self.parameters): portfolio.name
                for portfolio, time_window in portfolios_with_time_windows
            }

            for future in as_completed(future_to_portfolio):
                portfolio_name = future_to_portfolio[future]
                try:
                    name, result = future.result()
                    optimisation_results[name] = result
                    cfg.logger.info(f"Completed optimization for: {name}")
                except Exception as e:
                    cfg.logger.error(f"Error processing {portfolio_name}: {e}")

        return optimisation_results

    def _run_sequential(
        self, portfolios_with_time_windows: list[tuple[PortfolioPO, list[DateTime]]]
    ) -> dict[str, PortfolioOptimisationResult]:
        """
        Generic method to run optimization sequentially.

        :param portfolios_with_time_windows: List of tuples containing portfolios and their time windows
        :type portfolios_with_time_windows: list[tuple[PortfolioPO, list[DateTime]]]
        :return: Dictionary mapping portfolio names to optimization results
        :rtype: dict[str, PortfolioOptimisationResult]
        """
        optimisation_results: dict[str, PortfolioOptimisationResult] = {}

        for portfolio, time_window in portfolios_with_time_windows:
            try:
                name, result = optimise_single_portfolio(portfolio, time_window, self.parameters)
                optimisation_results[name] = result
                cfg.logger.info(f"Completed optimization for: {name}")
            except Exception as e:
                cfg.logger.error(f"Error processing {portfolio.name}: {e}")

        return optimisation_results

    def _optimise_portfolio_manual_activated(self, portfolio: PortfolioPO) -> PortfolioOptimisationResult:
        """
        Create a result object for manually activated portfolios.

        :param portfolio: Portfolio to manually activate
        :type portfolio: PortfolioPO
        :return: PortfolioOptimisationResult with manual activation applied
        :rtype: PortfolioOptimisationResult
        """
        cfg.logger.info(f"Manual activation for portfolio: {portfolio.name}")
        cfg.logger.debug("Manual activation optimisation not yet implemented")

        set_manual_activation(portfolio.equipments.get_all_equipment(), self.parameters)

        return PortfolioOptimisationResult(
            portfolio=portfolio, variable_values={}, solution_info=SolutionInfo(status=SolverStatus.NOT_SOLVED)
        )
