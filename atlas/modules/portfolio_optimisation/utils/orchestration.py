"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field

import atlas.config as cfg
from atlas.enums import SolverStatus
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.optim import PortfolioOptimisationModel
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
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
    is_manual_activation: bool = False

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
        return f"PortfolioOptimisationResult(portfolio={self.portfolio.name}, is_manual_activation={self.is_manual_activation})"


def optimise_single_portfolio(
    portfolio: PortfolioPO, parameters: PortfolioOptimisationParameters
) -> tuple[str, PortfolioOptimisationResult]:
    """
    Worker function for portfolio optimization (works for both multiprocessing and sequential).

    Builds and solves the optimization model, then extracts results into a picklable
    PortfolioOptimisationResult object (avoiding SWIG solver objects).

    :param portfolio: Portfolio to optimize
    :type portfolio: PortfolioPO
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
        model.build()

        if parameters.solver.export_lp:
            output_path = parameters.get_output_dir() / "lp_export"
            output_path.mkdir(parents=True, exist_ok=True)
            model.export_model(output_path / f"po_{portfolio.name}.lp")

        model.solve()

        variable_values = {var_name: model.get_variable_value(var_name) for var_name in model._variables_name}

        result = PortfolioOptimisationResult(
            portfolio=model.portfolio,
            variable_values=variable_values,
            solution_info=model.solution_info,
            is_manual_activation=False,
        )

        return portfolio.name, result

    except Exception as e:
        cfg.logger.error(f"Optimisation failed for portfolio {portfolio.name}. Falling back to manual activation: {e}")

        set_manual_activation(portfolio.equipments.get_all_equipment(), parameters)

        result = PortfolioOptimisationResult(
            portfolio=portfolio,
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.NOT_SOLVED),
            is_manual_activation=True,
        )

        return portfolio.name, result


def run_parallel(
    portfolios: list[PortfolioPO],
    parameters: PortfolioOptimisationParameters,
) -> dict[str, PortfolioOptimisationResult]:
    """
    Generic function to run optimization using multiprocessing.

    :param portfolios: List of portfolios to optimize
    :type portfolios: list[PortfolioPO]
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Dictionary mapping portfolio names to optimization results
    :rtype: dict[str, PortfolioOptimisationResult]
    """
    optimisation_results: dict[str, PortfolioOptimisationResult] = {}

    with ProcessPoolExecutor(max_workers=parameters.multiprocessing.max_workers) as executor:
        future_to_portfolio = {
            executor.submit(optimise_single_portfolio, portfolio, parameters): portfolio.name
            for portfolio in portfolios
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


def run_sequential(
    portfolios: list[PortfolioPO],
    parameters: PortfolioOptimisationParameters,
) -> dict[str, PortfolioOptimisationResult]:
    """
    Generic function to run optimization sequentially.

    :param portfolios: List of portfolios to optimize
    :type portfolios: list[PortfolioPO]
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Dictionary mapping portfolio names to optimization results
    :rtype: dict[str, PortfolioOptimisationResult]
    """
    optimisation_results: dict[str, PortfolioOptimisationResult] = {}

    for portfolio in portfolios:
        try:
            name, result = optimise_single_portfolio(portfolio, parameters)
            optimisation_results[name] = result
            cfg.logger.info(f"Completed optimization for: {name}")
        except Exception as e:
            cfg.logger.error(f"Error processing {portfolio.name}: {e}")

    return optimisation_results


def optimise_portfolio_manual_activated(
    portfolio: PortfolioPO, parameters: PortfolioOptimisationParameters
) -> PortfolioOptimisationResult:
    """
    Create a result object for manually activated portfolios.

    :param portfolio: Portfolio to manually activate
    :type portfolio: PortfolioPO
    :return: PortfolioOptimisationResult with manual activation applied
    :rtype: PortfolioOptimisationResult
    """
    cfg.logger.info(f"Manual activation for portfolio: {portfolio.name}")
    cfg.logger.debug("Manual activation optimisation not yet implemented")

    set_manual_activation(portfolio.equipments.get_all_equipment(), parameters)

    return PortfolioOptimisationResult(
        portfolio=portfolio, variable_values={}, solution_info=None, is_manual_activation=True
    )
