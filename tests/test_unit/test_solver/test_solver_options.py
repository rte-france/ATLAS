"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for SolverOptions functionality.
"""

from unittest.mock import MagicMock, patch

from atlas.enum import SolverEnum
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel


class TestSolverOptions:
    """Tests for SolverOptions class."""

    def test_default_options(self):
        """Test default options."""
        options = SolverOptions()
        assert options.presolve is True
        assert options.duality_gap is None
        assert options.time_limit is None

    def test_custom_options(self):
        """Test custom options."""
        options = SolverOptions(presolve=False, duality_gap=0.01, time_limit=60.0)
        assert options.presolve is False
        assert options.duality_gap == 0.01
        assert options.time_limit == 60.0


class TestOptimisationModelWithOptions:
    """Tests for OptimisationModel with SolverOptions."""

    def test_model_with_default_options(self):
        """Test model with default options."""
        model = OptimisationModel(solver_name=SolverEnum.GLOP)
        assert model.options.presolve is True
        assert model.options.duality_gap is None
        assert model.options.time_limit is None

    def test_model_with_custom_options(self):
        """Test model with custom options."""
        options = SolverOptions(presolve=False, duality_gap=0.01, time_limit=30.0)
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)
        assert model.options.presolve is False
        assert model.options.duality_gap == 0.01
        assert model.options.time_limit == 30.0

    def test_update_options(self):
        """Test updating options."""
        model = OptimisationModel(solver_name=SolverEnum.GLOP)
        model.set_solver_options(SolverOptions(duality_gap=0.05, time_limit=120.0))
        assert model.options.duality_gap == 0.05
        assert model.options.time_limit == 120.0


class TestSolverOptionsIntegration:
    """Integration tests for solver options."""

    def test_solve_with_options(self):
        """Test solving with options."""
        options = SolverOptions(presolve=True, duality_gap=0.01, time_limit=60.0)
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        x = model.add_continuous_variable("x", 0, 10)
        model.set_objective(x, direction="maximize")

        solution = model.solve()
        assert solution.status.name == "OPTIMAL"
        assert abs(model.get_variable_value("x") - 10.0) < 1e-6

    def test_options_persist_after_clear(self):
        """Test options persist after clear."""
        options = SolverOptions(duality_gap=0.02, time_limit=45.0)
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        model.add_continuous_variable("x", 0, 5)
        model.solve()
        model.clear()

        assert model.options.duality_gap == 0.02
        assert model.options.time_limit == 45.0
        assert len(model.variables) == 0


class TestSolverOptionsParameterPassing:
    """Tests that verify options are actually passed to the solver."""

    def test_presolve_disabled_passed_to_solver(self):
        """Test that presolve=False is passed to solver."""
        options = SolverOptions(presolve=False)
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        # Mock the underlying solver
        mock_solver = MagicMock()
        model._solver = mock_solver

        x = model.add_continuous_variable("x", 0, 10)
        model.set_objective(x, direction="maximize")
        model.solve()

        # Verify SetSolverSpecificParametersAsString was called with presolve off
        mock_solver.SetSolverSpecificParametersAsString.assert_called()
        call_args = mock_solver.SetSolverSpecificParametersAsString.call_args[0][0]
        assert "presolve off" in call_args

    def test_duality_gap_passed_to_solver(self):
        """Test that duality_gap is passed to solver."""
        options = SolverOptions(duality_gap=0.05)
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        # Mock the underlying solver
        mock_solver = MagicMock()
        model._solver = mock_solver

        x = model.add_continuous_variable("x", 0, 10)
        model.set_objective(x, direction="maximize")
        model.solve()

        # Verify SetSolverSpecificParametersAsString was called with duality gap
        mock_solver.SetSolverSpecificParametersAsString.assert_called()
        call_args = mock_solver.SetSolverSpecificParametersAsString.call_args[0][0]
        assert "relative_mip_gap 0.05" in call_args

    def test_time_limit_passed_to_solver(self):
        """Test that time_limit is passed to solver."""
        options = SolverOptions(time_limit=30.0)
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        # Mock the underlying solver
        mock_solver = MagicMock()
        model._solver = mock_solver

        x = model.add_continuous_variable("x", 0, 10)
        model.set_objective(x, direction="maximize")
        model.solve()

        # Verify SetTimeLimit was called with correct value (30.0 seconds = 30000 ms)
        mock_solver.SetTimeLimit.assert_called_once_with(30000)

    def test_all_options_passed_to_solver(self):
        """Test that all options are passed to solver together."""
        options = SolverOptions(presolve=False, duality_gap=0.02, time_limit=60.0)
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        # Mock the underlying solver
        mock_solver = MagicMock()
        model._solver = mock_solver

        x = model.add_continuous_variable("x", 0, 10)
        model.set_objective(x, direction="maximize")
        model.solve()

        # Verify SetSolverSpecificParametersAsString contains all options
        mock_solver.SetSolverSpecificParametersAsString.assert_called()
        call_args = mock_solver.SetSolverSpecificParametersAsString.call_args[0][0]
        assert "presolve off" in call_args
        assert "relative_mip_gap 0.02" in call_args

        # Verify SetTimeLimit was called
        mock_solver.SetTimeLimit.assert_called_once_with(60000)

    def test_default_options_no_parameters_set(self):
        """Test that default options don't set unnecessary parameters."""
        options = SolverOptions()  # All defaults
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        # Mock the underlying solver
        mock_solver = MagicMock()
        model._solver = mock_solver

        x = model.add_continuous_variable("x", 0, 10)
        model.set_objective(x, direction="maximize")
        model.solve()

        # With defaults (presolve=True, duality_gap=None, time_limit=None),
        # SetSolverSpecificParametersAsString should not be called
        mock_solver.SetSolverSpecificParametersAsString.assert_not_called()

        # SetTimeLimit should not be called
        mock_solver.SetTimeLimit.assert_not_called()
