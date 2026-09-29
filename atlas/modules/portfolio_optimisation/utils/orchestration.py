"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.enums import SolverStatus
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.optim import PortfolioOptimisationModel
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.modules.portfolio_optimisation.utils.manual_activation import set_manual_activation
from atlas.solver.models import SolutionInfo, SolverOptions

if TYPE_CHECKING:
    from pendulum import DateTime


@dataclass
class SinglePortfolioResult:
    """
    This class stores the optimization results without the unpicklable solver object,
    making it suitable for multiprocessing with ProcessPoolExecutor.

    :param portfolio: The optimized portfolio object
    :type portfolio: PortfolioPO
    :param solution_info: Dictionary containing solver status, objective value, and solve time
    :type solution_info: SolutionInfo | None
    :param solution: Solved values of each temporal variable, keyed by its name
        (see :meth:`~atlas.solver.solver_interface.OptimisationModel.solution`)
    :type solution: dict[str, Timeseries]
    :param time_window: First and last time read back from the solution, None to read it whole
    :type time_window: tuple[DateTime, DateTime] | None

    Reading a variable, ``result["unit_power_level"]``, restricts it to the time window: only
    the variables actually read back are sliced.
    """

    portfolio: PortfolioPO
    solution_info: SolutionInfo | None
    solution: dict[str, Timeseries] = field(default_factory=dict)
    time_window: tuple[DateTime, DateTime] | None = None
    is_manual_activation: bool = False

    def __getitem__(self, variable: str) -> Timeseries:
        """Return the solved values of *variable* over the time window."""
        values = self.solution[variable]
        return values if self.time_window is None else values.slice(*self.time_window, inplace=False)

    def __contains__(self, variable: str) -> bool:
        """Tell whether *variable* is part of the solution."""
        return variable in self.solution

    @property
    def name(self) -> str:
        """Get the portfolio name (for compatibility with model interface)."""
        return self.portfolio.name

    def __repr__(self) -> str:
        return (
            f"SinglePortfolioResult(portfolio={self.portfolio.name}, is_manual_activation={self.is_manual_activation})"
        )


def optimise_single_portfolio(
    portfolio: PortfolioPO, parameters: PortfolioOptimisationParameters
) -> SinglePortfolioResult:
    """
    Worker function for portfolio optimization (works for both multiprocessing and sequential).

    Builds and solves the optimization model, then extracts results into a picklable
    SinglePortfolioResult object (avoiding SWIG solver objects).

    :param portfolio: Portfolio to optimize
    :type portfolio: PortfolioPO
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Optimization result
    :rtype: SinglePortfolioResult
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
            output_path = parameters.lp_dir
            output_path.mkdir(parents=True, exist_ok=True)
            model.export_model(output_path / f"po_{portfolio.name}.lp")

        solution_info = model.solve()
        model.require_solution()

        result = SinglePortfolioResult(
            portfolio=model.portfolio,
            solution=model.solution(),
            time_window=(min(parameters.portfolio_time_window), max(parameters.portfolio_time_window)),
            solution_info=solution_info,
            is_manual_activation=False,
        )

        return result

    except Exception as e:
        cfg.logger.warning(
            f"Optimisation failed for portfolio {portfolio.name}, falling back to heuristic computation "
            f"(degraded result, workflow continues):{e}"
        )

        set_manual_activation(portfolio.equipments.get_all_equipment(), parameters)

        result = SinglePortfolioResult(
            portfolio=portfolio,
            solution_info=SolutionInfo(status=SolverStatus.NOT_SOLVED),
            is_manual_activation=True,
        )

        return result


def run_parallel(
    portfolios: list[PortfolioPO],
    parameters: PortfolioOptimisationParameters,
) -> list[SinglePortfolioResult]:
    """
    Generic function to run optimization using multiprocessing.

    :param portfolios: List of portfolios to optimize
    :type portfolios: list[PortfolioPO]
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: List of optimization results, one per portfolio
    :rtype: list[SinglePortfolioResult]
    :raises RuntimeError: any worker failure is propagated, named after the failing portfolio,
        so a partial result never flows on
    """
    optimisation_results: list[SinglePortfolioResult] = []

    with ProcessPoolExecutor(max_workers=parameters.multiprocessing.max_workers) as executor:
        future_to_portfolio = {
            executor.submit(optimise_single_portfolio, portfolio, parameters): portfolio.name
            for portfolio in portfolios
        }

        for future in as_completed(future_to_portfolio):
            portfolio_name = future_to_portfolio[future]
            # Solver failures are already handled in optimise_single_portfolio (degraded result);
            # anything reaching here is a worker crash and must not silently shrink the result list.
            try:
                result = future.result()
            except Exception as e:
                raise RuntimeError(f"Optimisation failed for portfolio {portfolio_name}") from e
            optimisation_results.append(result)
            cfg.logger.info(f"Completed optimization for: {portfolio_name}")

    return optimisation_results


def run_sequential(
    portfolios: list[PortfolioPO],
    parameters: PortfolioOptimisationParameters,
) -> list[SinglePortfolioResult]:
    """
    Generic function to run optimization sequentially.

    :param portfolios: List of portfolios to optimize
    :type portfolios: list[PortfolioPO]
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: List of optimization results, one per portfolio
    :rtype: list[SinglePortfolioResult]
    :raises RuntimeError: any failure is propagated, named after the failing portfolio,
        so a partial result never flows on
    """
    optimisation_results: list[SinglePortfolioResult] = []

    for portfolio in portfolios:
        try:
            result = optimise_single_portfolio(portfolio, parameters)
        except Exception as e:
            raise RuntimeError(f"Optimisation failed for portfolio {portfolio.name}") from e
        optimisation_results.append(result)
        cfg.logger.info(f"Completed optimization for: {result.name}")

    return optimisation_results


def optimise_portfolio_manual_activated(
    portfolio: PortfolioPO, parameters: PortfolioOptimisationParameters
) -> SinglePortfolioResult:
    """
    Create a result object for manually activated portfolios.

    :param portfolio: Portfolio to manually activate
    :type portfolio: PortfolioPO
    :return: SinglePortfolioResult with manual activation applied
    :rtype: SinglePortfolioResult
    """
    cfg.logger.info(f"Manual activation for portfolio: {portfolio.name}")
    cfg.logger.debug("Manual activation optimisation not yet implemented")

    set_manual_activation(portfolio.equipments.get_all_equipment(), parameters)

    return SinglePortfolioResult(portfolio=portfolio, solution_info=None, is_manual_activation=True)
