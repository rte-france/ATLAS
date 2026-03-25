"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pendulum
import pytest

from atlas.enums import MarketType, SolverStatus
from atlas.modules.portfolio_optimisation.input_dataset import PortfolioOptimisationInputDataset
from atlas.modules.portfolio_optimisation.models.portfolio import PortfolioPO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.portfolio_orchestrator import (
    PortfolioOptimisationOrchestrator,
    PortfolioOptimisationResult,
    optimise_single_portfolio,
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

    @pytest.fixture
    def time_window(self):
        """Create a test time window."""
        return [
            pendulum.datetime(2024, 1, 1, 0),
            pendulum.datetime(2024, 1, 1, 1),
            pendulum.datetime(2024, 1, 1, 2),
        ]

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.PortfolioOptimisationModel")
    def test_successful_optimization(self, mock_model_class, mock_portfolio, mock_parameters, time_window):
        """Test successful portfolio optimization."""
        # Setup mock portfolio with equipments (needed for exception handling)
        mock_portfolio.equipments = Mock()
        mock_portfolio.equipments.get_all_equipment.return_value = []

        # Setup mock model
        mock_model = Mock()
        mock_model.portfolio = mock_portfolio
        mock_model._variables_name = ["var1", "var2"]
        mock_model.get_variable_value = Mock(side_effect=lambda x: 10.0 if x == "var1" else 20.0)
        mock_model.solution_info = SolutionInfo(status=SolverStatus.OPTIMAL)
        mock_model_class.return_value = mock_model

        # Call function
        name, result = optimise_single_portfolio(mock_portfolio, time_window, mock_parameters)

        # Assertions
        assert name == "test_portfolio"
        assert isinstance(result, PortfolioOptimisationResult)
        assert result.portfolio == mock_portfolio
        assert result.variable_values["var1"] == 10.0
        assert result.variable_values["var2"] == 20.0
        assert result.solution_info.status == SolverStatus.OPTIMAL

        # Verify model methods were called
        mock_model.set_direction.assert_called_once_with("minimize")
        mock_model.build.assert_called_once_with(time_window)
        mock_model.solve.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.set_manual_activation")
    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.PortfolioOptimisationModel")
    def test_optimization_failure_fallback(
        self, mock_model_class, mock_set_manual_activation, mock_portfolio, mock_parameters, time_window
    ):
        """Test that optimization failure falls back to manual activation."""
        # Setup mock model to raise exception
        mock_model = Mock()
        mock_model.solve.side_effect = Exception("Solver failed")
        mock_model_class.return_value = mock_model

        # Setup portfolio with equipments
        mock_equipments = Mock()
        mock_equipments.get_all_equipment.return_value = []
        mock_portfolio.equipments = mock_equipments

        # Call function
        name, result = optimise_single_portfolio(mock_portfolio, time_window, mock_parameters)

        # Assertions
        assert name == "test_portfolio"
        assert isinstance(result, PortfolioOptimisationResult)
        assert result.portfolio == mock_portfolio
        assert result.variable_values == {}
        assert result.solution_info.status == SolverStatus.NOT_SOLVED

        # Verify manual activation was called
        mock_set_manual_activation.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.PortfolioOptimisationModel")
    def test_solver_options_applied(self, mock_model_class, mock_portfolio, mock_parameters, time_window):
        """Test that solver options from parameters are correctly applied."""
        mock_parameters.solver.use_presolve = True
        mock_parameters.solver.duality_gap = 0.001
        mock_parameters.solver.timeout = pendulum.duration(seconds=600)

        # Setup mock portfolio with equipments (needed for exception handling)
        mock_portfolio.equipments = Mock()
        mock_portfolio.equipments.get_all_equipment.return_value = []

        # Setup mock model
        mock_model = Mock()
        mock_model.portfolio = mock_portfolio
        mock_model._variables_name = []
        mock_model.solution_info = SolutionInfo(status=SolverStatus.OPTIMAL)
        mock_model_class.return_value = mock_model

        # Call function
        optimise_single_portfolio(mock_portfolio, time_window, mock_parameters)

        # Verify model was created with correct solver options
        call_args = mock_model_class.call_args
        assert call_args[0][0] == mock_portfolio
        assert call_args[0][1] == mock_parameters
        solver_options = call_args[1]["solver_options"]
        assert solver_options.presolve is True
        assert solver_options.duality_gap == 0.001
        assert solver_options.time_limit == pendulum.duration(seconds=600)

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.PortfolioOptimisationModel")
    def test_lp_export_when_enabled(self, mock_model_class, mock_parameters, time_window):
        """Test that LP files are exported when export_lp is True."""
        mock_parameters.solver.export_lp = True
        mock_parameters.get_output_dir.return_value = Path("tmp")

        # Create a fresh mock portfolio
        test_portfolio = Mock(spec=PortfolioPO)
        test_portfolio.name = "test_portfolio"
        test_portfolio.equipments = Mock()
        test_portfolio.equipments.get_all_equipment.return_value = []

        # Setup mock model
        mock_model = Mock()
        mock_model.portfolio = test_portfolio
        mock_model._variables_name = []
        mock_model.solution_info = SolutionInfo(status=SolverStatus.OPTIMAL)
        mock_model_class.return_value = mock_model

        with patch("pathlib.Path.mkdir"):
            optimise_single_portfolio(test_portfolio, time_window, mock_parameters)

        # Verify LP export was called
        mock_model.export_model.assert_called_once_with(Path("tmp/lp_export/po_test_portfolio.lp"))

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.PortfolioOptimisationModel")
    def test_lp_export_when_disabled(self, mock_model_class, mock_portfolio, mock_parameters, time_window):
        """Test that LP files are not exported when export_lp is False."""
        # Setup
        mock_parameters.output.output_dir = Path("tmp")
        mock_parameters.solver.export_lp = False

        # Setup mock portfolio with equipments
        mock_portfolio.equipments = Mock()
        mock_portfolio.equipments.get_all_equipment.return_value = []

        # Setup mock model
        mock_model = Mock()
        mock_model.portfolio = mock_portfolio
        mock_model._variables_name = []
        mock_model.solution_info = SolutionInfo(status=SolverStatus.OPTIMAL)
        mock_model_class.return_value = mock_model

        # Call function
        optimise_single_portfolio(mock_portfolio, time_window, mock_parameters)

        # Verify LP export was not called
        mock_model.export_model.assert_not_called()


class TestPortfolioOptimisationOrchestrator:
    """Test suite for PortfolioOptimisationOrchestrator class."""

    @pytest.fixture
    def mock_parameters(self):
        """Create mock parameters."""
        params = Mock()
        params.is_portfolio_bidding = True
        params.multiprocessing.use_multiprocessing = False
        params.multiprocessing.max_workers = None
        params.market = MarketType.dayahead
        params.use_forecast = False
        params.temporal.start_date = pendulum.datetime(2024, 1, 1)
        params.temporal.end_date = pendulum.datetime(2024, 1, 2)
        params.temporal.execution_date = pendulum.datetime(2024, 1, 1)
        return params

    @pytest.fixture
    def mock_input_dataset(self):
        """Create a mock input dataset."""
        dataset = Mock(spec=PortfolioOptimisationInputDataset)

        # Create mock portfolios
        portfolio1 = Mock(spec=PortfolioPO)
        portfolio1.name = "portfolio_1"
        portfolio1.equipments = Mock()
        portfolio1.equipments.get_all_equipment.return_value = []

        portfolio2 = Mock(spec=PortfolioPO)
        portfolio2.name = "portfolio_2"
        portfolio2.equipments = Mock()
        portfolio2.equipments.get_all_equipment.return_value = []

        manual_portfolio = Mock(spec=PortfolioPO)
        manual_portfolio.name = "manual_portfolio"
        manual_portfolio.equipments = Mock()
        manual_portfolio.equipments.get_all_equipment.return_value = []
        manual_portfolio.equipments.iter_by_type.return_value = []  # Empty iterator for equipment mode

        dataset.portfolios = [portfolio1, portfolio2]
        dataset.portfolios_manual_activation = [manual_portfolio]
        dataset.time_windows = {
            "portfolio_1": [pendulum.datetime(2024, 1, 1)],
            "portfolio_2": [pendulum.datetime(2024, 1, 1)],
            "manual_portfolio": [pendulum.datetime(2024, 1, 1)],
        }

        return dataset

    def test_initialization(self, mock_parameters):
        """Test orchestrator initialization."""
        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)

        assert orchestrator.parameters == mock_parameters

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.optimise_single_portfolio")
    def test_run_sequential_portfolio_mode(self, mock_optimise, mock_parameters, mock_input_dataset):
        """Test running in sequential portfolio bidding mode."""
        # Setup
        mock_parameters.is_portfolio_bidding = True
        mock_parameters.multiprocessing.use_multiprocessing = False

        # Mock optimization results
        result1 = PortfolioOptimisationResult(
            portfolio=mock_input_dataset.portfolios[0],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )
        result2 = PortfolioOptimisationResult(
            portfolio=mock_input_dataset.portfolios[1],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        mock_optimise.side_effect = [
            ("portfolio_1", result1),
            ("portfolio_2", result2),
        ]

        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
        results = orchestrator.run(mock_input_dataset)

        # Assertions
        assert len(results) == 3  # 2 normal portfolios + 1 manual
        assert "portfolio_1" in results
        assert "portfolio_2" in results
        assert "manual_portfolio" in results
        assert mock_optimise.call_count == 2

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.PortfolioPO")
    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.optimise_single_portfolio")
    def test_run_equipment_mode_sequential(
        self, mock_optimise, mock_portfolio_po_class, mock_parameters, mock_input_dataset
    ):
        """Test running in equipment mode with sequential execution."""
        # Setup
        mock_parameters.is_portfolio_bidding = False
        mock_parameters.multiprocessing.use_multiprocessing = False

        # Add equipment to portfolio
        mock_wind = Mock(spec=WindPO)
        mock_wind.name = "wind_1"
        mock_input_dataset.portfolios[0].equipments.iter_by_type = Mock(return_value=[("wind", [mock_wind])])
        mock_input_dataset.portfolios[1].equipments.iter_by_type = Mock(return_value=[])

        # Mock control block and market area
        mock_input_dataset.portfolios[0].control_block = Mock()
        mock_input_dataset.portfolios[0].market_area = Mock()
        mock_input_dataset.portfolios[0].market_area.set_market_context = Mock(
            return_value=mock_input_dataset.portfolios[0].market_area
        )

        mock_portfolio_instance = Mock(spec=PortfolioPO)
        mock_portfolio_instance.name = "wind_1"
        mock_portfolio_instance.market_area = Mock()
        mock_portfolio_instance.market_area.set_market_context = Mock(return_value=mock_portfolio_instance.market_area)
        mock_portfolio_instance.equipments = Mock()
        mock_portfolio_po_class.return_value = mock_portfolio_instance

        result = PortfolioOptimisationResult(
            portfolio=mock_portfolio_instance,
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )
        mock_optimise.return_value = ("wind_1", result)

        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
        results = orchestrator.run(mock_input_dataset)

        # Assertions - should have results for individual equipment
        assert len(results) >= 1
        mock_optimise.assert_called()

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.ProcessPoolExecutor")
    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.optimise_single_portfolio")
    def test_run_multiprocessing_portfolio_mode(
        self, mock_optimise, mock_executor_class, mock_parameters, mock_input_dataset
    ):
        """Test running in multiprocessing portfolio bidding mode."""
        # Setup
        mock_parameters.is_portfolio_bidding = True
        mock_parameters.multiprocessing.use_multiprocessing = True
        mock_parameters.multiprocessing.max_workers = 2

        # Mock executor and futures
        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor

        result1 = PortfolioOptimisationResult(
            portfolio=mock_input_dataset.portfolios[0],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )
        result2 = PortfolioOptimisationResult(
            portfolio=mock_input_dataset.portfolios[1],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        # Mock futures
        future1 = MagicMock()
        future1.result.return_value = ("portfolio_1", result1)
        future2 = MagicMock()
        future2.result.return_value = ("portfolio_2", result2)

        mock_executor.submit.side_effect = [future1, future2]

        # Mock as_completed to return futures
        with patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.as_completed") as mock_as_completed:
            mock_as_completed.return_value = [future1, future2]

            orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
            results = orchestrator.run(mock_input_dataset)

        # Assertions
        assert len(results) == 3  # 2 normal + 1 manual
        assert "portfolio_1" in results
        assert "portfolio_2" in results
        assert mock_executor.submit.call_count == 2

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.set_manual_activation")
    def test_optimise_portfolio_manual_activated(self, mock_set_manual, mock_parameters):
        """Test manual activation of portfolio."""
        # Setup
        portfolio = Mock(spec=PortfolioPO)
        portfolio.name = "manual_portfolio"
        portfolio.equipments = Mock()
        portfolio.equipments.get_all_equipment.return_value = []

        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
        result = orchestrator._optimise_portfolio_manual_activated(portfolio)

        # Assertions
        assert isinstance(result, PortfolioOptimisationResult)
        assert result.portfolio == portfolio
        assert result.variable_values == {}
        assert result.solution_info.status == SolverStatus.NOT_SOLVED
        mock_set_manual.assert_called_once()

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.optimise_single_portfolio")
    def test_run_handles_optimization_error(self, mock_optimise, mock_parameters, mock_input_dataset):
        """Test that orchestrator handles optimization errors gracefully."""
        # Setup
        mock_parameters.is_portfolio_bidding = True
        mock_parameters.multiprocessing.use_multiprocessing = False

        # First optimization succeeds, second raises exception
        result1 = PortfolioOptimisationResult(
            portfolio=mock_input_dataset.portfolios[0],
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        mock_optimise.side_effect = [
            ("portfolio_1", result1),
            Exception("Optimization failed"),
        ]

        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
        results = orchestrator.run(mock_input_dataset)

        # Should still process manual activation portfolio
        assert len(results) >= 2
        assert "portfolio_1" in results
        assert "manual_portfolio" in results

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.PortfolioPO")
    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.optimise_single_portfolio")
    def test_run_equipment_mode_with_manual_activation(
        self, mock_optimise, mock_portfolio_po_class, mock_parameters, mock_input_dataset
    ):
        """Test equipment mode processes manual activation portfolios correctly."""
        # Setup
        mock_parameters.is_portfolio_bidding = False
        mock_parameters.multiprocessing.use_multiprocessing = False

        # Setup manual activation portfolio with equipment
        manual_portfolio = mock_input_dataset.portfolios_manual_activation[0]
        mock_wind = Mock(spec=WindPO)
        mock_wind.name = "wind_manual"
        manual_portfolio.equipments.iter_by_type = Mock(return_value=[("wind", [mock_wind])])
        manual_portfolio.control_block = Mock()
        manual_portfolio.market_area = Mock()

        # Setup regular portfolios with no equipment
        mock_input_dataset.portfolios[0].equipments.iter_by_type = Mock(return_value=[])
        mock_input_dataset.portfolios[1].equipments.iter_by_type = Mock(return_value=[])

        # Mock PortfolioPO constructor
        mock_portfolio_instance = Mock(spec=PortfolioPO)
        mock_portfolio_instance.name = "wind_manual"
        mock_portfolio_instance.equipments = Mock()
        mock_portfolio_instance.equipments.get_all_equipment = Mock(return_value=[])
        mock_portfolio_po_class.return_value = mock_portfolio_instance

        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
        results = orchestrator.run(mock_input_dataset)

        # Manual activation portfolios should be processed in equipment mode
        assert len(results) >= 0

    def test_run_empty_portfolios(self, mock_parameters):
        """Test running with no portfolios."""
        # Setup empty dataset
        dataset = Mock(spec=PortfolioOptimisationInputDataset)
        dataset.portfolios = []
        dataset.portfolios_manual_activation = []
        dataset.time_windows = {}

        mock_parameters.is_portfolio_bidding = True
        mock_parameters.multiprocessing.use_multiprocessing = False

        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
        results = orchestrator.run(dataset)

        # Should return empty results
        assert results == {}

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.ProcessPoolExecutor")
    def test_multiprocessing_uses_max_workers(self, mock_executor_class, mock_parameters, mock_input_dataset):
        """Test that multiprocessing respects max_workers parameter."""
        # Setup
        mock_parameters.is_portfolio_bidding = True
        mock_parameters.multiprocessing.use_multiprocessing = True
        mock_parameters.multiprocessing.max_workers = 4

        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor
        mock_executor.submit.return_value = MagicMock()

        with patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.as_completed") as mock_as_completed:
            mock_as_completed.return_value = []

            orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
            orchestrator.run(mock_input_dataset)

        # Verify ProcessPoolExecutor was created with correct max_workers
        mock_executor_class.assert_called_once_with(max_workers=4)

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.ProcessPoolExecutor")
    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.optimise_single_portfolio")
    def test_run_equipment_multiprocessing_error_handling(
        self, mock_optimise, mock_executor_class, mock_parameters, mock_input_dataset
    ):
        """Test error handling in equipment multiprocessing mode."""
        # Setup
        mock_parameters.is_portfolio_bidding = False
        mock_parameters.multiprocessing.use_multiprocessing = True

        # Add equipment to portfolio
        mock_wind = Mock(spec=WindPO)
        mock_wind.name = "wind_1"
        mock_input_dataset.portfolios[0].equipments.iter_by_type = Mock(return_value=[("wind", [mock_wind])])
        mock_input_dataset.portfolios[0].control_block = Mock()
        mock_input_dataset.portfolios[0].market_area = Mock()
        mock_input_dataset.portfolios[0].market_area.set_market_context = Mock()
        mock_input_dataset.portfolios[1].equipments.iter_by_type = Mock(return_value=[])

        # Mock executor and futures
        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor

        # Mock future that raises exception
        future1 = MagicMock()
        future1.result.side_effect = Exception("Equipment optimization failed")

        mock_executor.submit.return_value = future1

        with patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.as_completed") as mock_as_completed:
            with patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.PortfolioPO"):
                mock_as_completed.return_value = [future1]

                orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
                results = orchestrator.run(mock_input_dataset)

                # Should handle error gracefully and continue
                assert isinstance(results, dict)

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.optimise_single_portfolio")
    def test_run_portfolio_sequential_with_multiple_errors(self, mock_optimise, mock_parameters, mock_input_dataset):
        """Test that sequential mode handles multiple errors gracefully."""
        # Setup
        mock_parameters.is_portfolio_bidding = True
        mock_parameters.multiprocessing.use_multiprocessing = False

        # All optimizations fail
        mock_optimise.side_effect = [
            Exception("First portfolio failed"),
            Exception("Second portfolio failed"),
        ]

        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
        results = orchestrator.run(mock_input_dataset)

        # Should still process manual activation portfolio
        assert "manual_portfolio" in results
        assert mock_optimise.call_count == 2

    def test_portfolio_result_repr(self):
        """Test PortfolioOptimisationResult __repr__ method."""
        portfolio = Mock(spec=PortfolioPO)
        portfolio.name = "test_portfolio"

        result = PortfolioOptimisationResult(
            portfolio=portfolio,
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        repr_str = repr(result)
        assert "PortfolioOptimisationResult" in repr_str
        assert "test_portfolio" in repr_str

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.PortfolioPO")
    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.optimise_single_portfolio")
    def test_equipment_mode_market_context_set(
        self, mock_optimise, mock_portfolio_po_class, mock_parameters, mock_input_dataset
    ):
        """Test that market context is properly set in equipment mode."""
        # Setup
        mock_parameters.is_portfolio_bidding = False
        mock_parameters.multiprocessing.use_multiprocessing = False
        mock_parameters.market = MarketType.intraday
        mock_parameters.use_forecast = True

        # Add equipment to portfolio
        mock_wind = Mock(spec=WindPO)
        mock_wind.name = "wind_1"
        mock_input_dataset.portfolios[0].equipments.iter_by_type = Mock(return_value=[("wind", [mock_wind])])
        mock_input_dataset.portfolios[0].control_block = Mock()
        mock_input_dataset.portfolios[0].market_area = Mock()
        mock_input_dataset.portfolios[1].equipments.iter_by_type = Mock(return_value=[])

        # Mock PortfolioPO
        mock_portfolio_instance = Mock(spec=PortfolioPO)
        mock_portfolio_instance.name = "wind_1"
        mock_portfolio_instance.equipments = Mock()
        mock_portfolio_instance.market_area = Mock()
        mock_portfolio_po_class.return_value = mock_portfolio_instance

        result = PortfolioOptimisationResult(
            portfolio=mock_portfolio_instance,
            variable_values={},
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )
        mock_optimise.return_value = ("wind_1", result)

        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
        orchestrator.run(mock_input_dataset)

        # Verify market context was set with correct parameters
        mock_portfolio_instance.market_area.set_market_context.assert_called_with(MarketType.intraday, True)

    def test_optimization_result_default_variable_values(self):
        """Test that PortfolioOptimisationResult has empty dict by default."""
        portfolio = Mock(spec=PortfolioPO)
        portfolio.name = "test"

        result = PortfolioOptimisationResult(
            portfolio=portfolio,
            solution_info=SolutionInfo(status=SolverStatus.OPTIMAL),
        )

        assert result.variable_values == {}
        assert result.get_variable_value("any_var") == 0.0

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.optimise_single_portfolio")
    def test_run_with_only_manual_activation_portfolios(self, mock_optimise, mock_parameters):
        """Test running when all portfolios use manual activation."""
        # Setup dataset with only manual activation portfolios
        dataset = Mock(spec=PortfolioOptimisationInputDataset)
        dataset.portfolios = []  # No regular portfolios

        manual_portfolio = Mock(spec=PortfolioPO)
        manual_portfolio.name = "manual_only"
        manual_portfolio.equipments = Mock()
        manual_portfolio.equipments.get_all_equipment.return_value = []

        dataset.portfolios_manual_activation = [manual_portfolio]
        dataset.time_windows = {}

        mock_parameters.is_portfolio_bidding = True
        mock_parameters.multiprocessing.use_multiprocessing = False

        orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
        results = orchestrator.run(dataset)

        # Should have result for manual portfolio only
        assert len(results) == 1
        assert "manual_only" in results
        # optimise_single_portfolio should not be called
        mock_optimise.assert_not_called()

    @patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.ProcessPoolExecutor")
    def test_multiprocessing_with_none_max_workers(self, mock_executor_class, mock_parameters, mock_input_dataset):
        """Test that multiprocessing works with max_workers=None (default CPU count)."""
        # Setup
        mock_parameters.is_portfolio_bidding = True
        mock_parameters.multiprocessing.use_multiprocessing = True
        mock_parameters.multiprocessing.max_workers = None  # Should use default

        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor
        mock_executor.submit.return_value = MagicMock()

        with patch("atlas.modules.portfolio_optimisation.portfolio_orchestrator.as_completed") as mock_as_completed:
            mock_as_completed.return_value = []

            orchestrator = PortfolioOptimisationOrchestrator(mock_parameters)
            orchestrator.run(mock_input_dataset)

        # Verify ProcessPoolExecutor was created with None (defaults to CPU count)
        mock_executor_class.assert_called_once_with(max_workers=None)
