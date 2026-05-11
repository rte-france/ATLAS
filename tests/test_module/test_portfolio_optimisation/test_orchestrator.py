"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pendulum
import pytest

from atlas.enums import MarketType, SolverStatus
from atlas.modules.portfolio_optimisation.input_objects.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.utils.orchestration import (
    PortfolioOptimisationResult,
    optimise_portfolio_manual_activated,
    optimise_single_portfolio,
    run_parallel,
    run_sequential,
)
from atlas.solver.models import SolutionInfo


class TestPortfolioOptimisationResult:
    """Test suite for PortfolioOptimisationResult dataclass."""

    def test_get_variable_value_existing(self):
        """Test getting value of an existing variable."""
        portfolio = Mock(spec=PortfolioPO)
        portfolio.name = "test_portfolio"

        result = PortfolioOptimisationResult(
            portfolio=portfolio,
            variable_values={"var1": 10.5, "var2": 20.0},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        assert result.get_variable_value("var1") == 10.5
        assert result.get_variable_value("var2") == 20.0

    def test_get_variable_value_non_existing(self):
        """Test getting value of a non-existing variable returns 0.0."""
        portfolio = Mock(spec=PortfolioPO)
        portfolio.name = "test_portfolio"

        result = PortfolioOptimisationResult(
            portfolio=portfolio,
            variable_values={"var1": 10.5},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        assert result.get_variable_value("non_existing") == 0.0

    def test_name_property(self):
        """Test that name property returns portfolio name."""
        portfolio = Mock(spec=PortfolioPO)
        portfolio.name = "test_portfolio"

        result = PortfolioOptimisationResult(
            portfolio=portfolio,
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        assert result.name == "test_portfolio"


class TestOptimiseSinglePortfolio:
    """Test suite for optimise_single_portfolio function."""

    @pytest.fixture
    def mock_portfolio(self):
        """Create a mock portfolio."""
        portfolio = Mock(spec=PortfolioPO)
        portfolio.name = "test_portfolio"
        return portfolio

    @pytest.fixture
    def mock_parameters(self):
        """Create mock parameters."""
        params = Mock()
        params.solver.use_presolve = False
        params.solver.duality_gap = 0.0001
        params.solver.timeout = pendulum.duration(seconds=300)
        params.market = MarketType.dayahead
        params.solver.export_lp = False
        return params

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.PortfolioOptimisationModel")
    def test_successful_optimization(self, mock_model_class, mock_portfolio, mock_parameters):
        """Test successful portfolio optimization."""
        mock_portfolio.equipments = Mock()
        mock_portfolio.equipments.get_all_equipment.return_value = []

        mock_model = Mock()
        mock_model.portfolio = mock_portfolio
        mock_model._variables_name = ["var1", "var2"]
        mock_model.get_variable_value = Mock(side_effect=lambda x: 10.0 if x == "var1" else 20.0)
        mock_model.solution_info = SolutionInfo(status=SolverStatus.OPTIMAL)
        mock_model_class.return_value = mock_model

        name, result = optimise_single_portfolio(mock_portfolio, mock_parameters)

        assert name == "test_portfolio"
        assert isinstance(result, PortfolioOptimisationResult)
        assert result.portfolio == mock_portfolio
        assert result.variable_values["var1"] == 10.0
        assert result.variable_values["var2"] == 20.0
        assert result.solution_info.status == SolverStatus.OPTIMAL

        mock_model.set_direction.assert_called_once_with("minimize")
        mock_model.build.assert_called_once_with()
        mock_model.solve.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.set_manual_activation")
    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.PortfolioOptimisationModel")
    def test_optimization_failure_fallback(
        self, mock_model_class, mock_set_manual_activation, mock_portfolio, mock_parameters
    ):
        """Test that optimization failure falls back to manual activation."""
        mock_model = Mock()
        mock_model.solve.side_effect = Exception("Solver failed")
        mock_model_class.return_value = mock_model

        mock_equipments = Mock()
        mock_equipments.get_all_equipment.return_value = []
        mock_portfolio.equipments = mock_equipments

        name, result = optimise_single_portfolio(mock_portfolio, mock_parameters)

        assert name == "test_portfolio"
        assert isinstance(result, PortfolioOptimisationResult)
        assert result.portfolio == mock_portfolio
        assert result.variable_values == {}
        assert result.solution_info.status == SolverStatus.NOT_SOLVED
        mock_set_manual_activation.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.PortfolioOptimisationModel")
    def test_solver_options_applied(self, mock_model_class, mock_portfolio, mock_parameters):
        """Test that solver options from parameters are correctly applied."""
        mock_parameters.solver.use_presolve = True
        mock_parameters.solver.duality_gap = 0.001
        mock_parameters.solver.timeout = pendulum.duration(seconds=600)

        mock_portfolio.equipments = Mock()
        mock_portfolio.equipments.get_all_equipment.return_value = []

        mock_model = Mock()
        mock_model.portfolio = mock_portfolio
        mock_model._variables_name = []
        mock_model.solution_info = SolutionInfo(status=SolverStatus.OPTIMAL)
        mock_model_class.return_value = mock_model

        optimise_single_portfolio(mock_portfolio, mock_parameters)

        call_args = mock_model_class.call_args
        assert call_args[0][0] == mock_portfolio
        assert call_args[0][1] == mock_parameters
        solver_options = call_args[1]["solver_options"]
        assert solver_options.presolve is True
        assert solver_options.duality_gap == 0.001
        assert solver_options.time_limit == pendulum.duration(seconds=600)

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.PortfolioOptimisationModel")
    def test_lp_export_when_enabled(self, mock_model_class, mock_parameters):
        """Test that LP files are exported when export_lp is True."""
        mock_parameters.solver.export_lp = True
        mock_parameters.get_output_dir.return_value = Path("tmp")

        test_portfolio = Mock(spec=PortfolioPO)
        test_portfolio.name = "test_portfolio"
        test_portfolio.equipments = Mock()
        test_portfolio.equipments.get_all_equipment.return_value = []

        mock_model = Mock()
        mock_model.portfolio = test_portfolio
        mock_model._variables_name = []
        mock_model.solution_info = SolutionInfo(status=SolverStatus.OPTIMAL)
        mock_model_class.return_value = mock_model

        with patch("pathlib.Path.mkdir"):
            optimise_single_portfolio(test_portfolio, mock_parameters)

        mock_model.export_model.assert_called_once_with(Path("tmp/lp_export/po_test_portfolio.lp"))

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.PortfolioOptimisationModel")
    def test_lp_export_when_disabled(self, mock_model_class, mock_portfolio, mock_parameters):
        """Test that LP files are not exported when export_lp is False."""
        mock_parameters.output.output_dir = Path("tmp")
        mock_parameters.solver.export_lp = False

        mock_portfolio.equipments = Mock()
        mock_portfolio.equipments.get_all_equipment.return_value = []

        mock_model = Mock()
        mock_model.portfolio = mock_portfolio
        mock_model._variables_name = []
        mock_model.solution_info = SolutionInfo(status=SolverStatus.OPTIMAL)
        mock_model_class.return_value = mock_model

        optimise_single_portfolio(mock_portfolio, mock_parameters)

        mock_model.export_model.assert_not_called()


class TestRunSequential:
    """Test suite for run_sequential function."""

    @pytest.fixture
    def mock_parameters(self):
        """Create mock parameters."""
        params = Mock()
        params.solver.use_presolve = False
        params.solver.duality_gap = 0.0001
        params.solver.timeout = pendulum.duration(seconds=300)
        params.solver.export_lp = False
        return params

    @pytest.fixture
    def portfolios(self):
        """Create test portfolios."""
        portfolio1 = Mock(spec=PortfolioPO)
        portfolio1.name = "portfolio_1"
        portfolio1.equipments = Mock()
        portfolio1.equipments.get_all_equipment.return_value = []

        portfolio2 = Mock(spec=PortfolioPO)
        portfolio2.name = "portfolio_2"
        portfolio2.equipments = Mock()
        portfolio2.equipments.get_all_equipment.return_value = []

        return [portfolio1, portfolio2]

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.optimise_single_portfolio")
    def test_run_sequential_success(self, mock_optimise, portfolios, mock_parameters):
        """Test run_sequential processes all portfolios successfully."""
        result1 = PortfolioOptimisationResult(
            portfolio=portfolios[0],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )
        result2 = PortfolioOptimisationResult(
            portfolio=portfolios[1],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        mock_optimise.side_effect = [("portfolio_1", result1), ("portfolio_2", result2)]

        results = run_sequential(portfolios, mock_parameters)

        assert len(results) == 2
        assert "portfolio_1" in results
        assert "portfolio_2" in results
        assert mock_optimise.call_count == 2

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.optimise_single_portfolio")
    def test_run_sequential_handles_errors(self, mock_optimise, portfolios, mock_parameters):
        """Test run_sequential handles errors gracefully."""
        result1 = PortfolioOptimisationResult(
            portfolio=portfolios[0],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        mock_optimise.side_effect = [("portfolio_1", result1), Exception("Optimization failed")]

        results = run_sequential(portfolios, mock_parameters)

        assert len(results) == 1
        assert "portfolio_1" in results


class TestRunParallel:
    """Test suite for run_parallel function."""

    @pytest.fixture
    def mock_parameters(self):
        """Create mock parameters."""
        params = Mock()
        params.multiprocessing.max_workers = 2
        return params

    @pytest.fixture
    def portfolios(self):
        """Create test portfolios."""
        portfolio1 = Mock(spec=PortfolioPO)
        portfolio1.name = "portfolio_1"
        portfolio2 = Mock(spec=PortfolioPO)
        portfolio2.name = "portfolio_2"
        return [portfolio1, portfolio2]

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.ProcessPoolExecutor")
    def test_run_parallel_success(self, mock_executor_class, portfolios, mock_parameters):
        """Test run_parallel processes all portfolios successfully."""
        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor

        result1 = PortfolioOptimisationResult(
            portfolio=portfolios[0],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )
        result2 = PortfolioOptimisationResult(
            portfolio=portfolios[1],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        future1 = MagicMock()
        future1.result.return_value = ("portfolio_1", result1)
        future2 = MagicMock()
        future2.result.return_value = ("portfolio_2", result2)

        mock_executor.submit.side_effect = [future1, future2]

        with patch("atlas.modules.portfolio_optimisation.utils.orchestration.as_completed") as mock_as_completed:
            mock_as_completed.return_value = [future1, future2]

            results = run_parallel(portfolios, mock_parameters)

        assert len(results) == 2
        assert "portfolio_1" in results
        assert "portfolio_2" in results
        mock_executor_class.assert_called_once_with(max_workers=2)

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.ProcessPoolExecutor")
    def test_run_parallel_handles_errors(self, mock_executor_class, portfolios, mock_parameters):
        """Test run_parallel handles errors gracefully."""
        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor

        result1 = PortfolioOptimisationResult(
            portfolio=portfolios[0],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )
        future1 = MagicMock()
        future1.result.return_value = ("portfolio_1", result1)

        future2 = MagicMock()
        future2.result.side_effect = Exception("Optimization failed")

        mock_executor.submit.side_effect = [future1, future2]

        with patch("atlas.modules.portfolio_optimisation.utils.orchestration.as_completed") as mock_as_completed:
            mock_as_completed.return_value = [future1, future2]

            results = run_parallel(portfolios, mock_parameters)

        assert len(results) == 1
        assert "portfolio_1" in results


class TestOptimisePortfolioManualActivated:
    """Test suite for optimise_portfolio_manual_activated function."""

    @pytest.fixture
    def mock_parameters(self):
        """Create mock parameters."""
        return Mock()

    @patch("atlas.modules.portfolio_optimisation.utils.orchestration.set_manual_activation")
    def test_manual_activation(self, mock_set_manual, mock_parameters):
        """Test manual activation of portfolio."""
        portfolio = Mock(spec=PortfolioPO)
        portfolio.name = "manual_portfolio"
        portfolio.equipments = Mock()
        portfolio.equipments.get_all_equipment.return_value = []

        result = optimise_portfolio_manual_activated(portfolio, mock_parameters)

        # Assertions
        assert isinstance(result, PortfolioOptimisationResult)
        assert result.portfolio == portfolio
        assert result.variable_values == {}
        assert result.solution_info is None
        mock_set_manual.assert_called_once_with([], mock_parameters)
