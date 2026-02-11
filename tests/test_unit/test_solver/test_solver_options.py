"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for SolverOptions functionality.
"""

from unittest.mock import MagicMock

from pendulum import duration

from atlas.enums import SolverEnum
from atlas.solver.models import SolverOptions
from atlas.solver.solver_interface import OptimisationModel
from tests.conftest import requires_xpress


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
        options = SolverOptions(presolve=False, duality_gap=0.01, time_limit=duration(seconds=60))
        assert options.presolve is False
        assert options.duality_gap == 0.01
        assert options.time_limit == duration(seconds=60)


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
        options = SolverOptions(presolve=False, duality_gap=0.01, time_limit=duration(seconds=30))
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)
        assert model.options.presolve is False
        assert model.options.duality_gap == 0.01
        assert model.options.time_limit == duration(seconds=30)

    def test_update_options(self):
        """Test updating options."""
        model = OptimisationModel(solver_name=SolverEnum.GLOP)
        model.set_solver_options(SolverOptions(duality_gap=0.05, time_limit=duration(seconds=120)))
        assert model.options.duality_gap == 0.05
        assert model.options.time_limit == duration(seconds=120)


class TestSolverOptionsIntegration:
    """Integration tests for solver options."""

    def test_solve_with_options(self):
        """Test solving with options."""
        options = SolverOptions(presolve=True, duality_gap=0.01, time_limit=duration(seconds=60))
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        x = model.add_continuous_variable("x", 0, 10)
        model.set_direction("maximize")
        model.set_objective(x)

        solution = model.solve()
        assert solution.status.name == "OPTIMAL"
        assert abs(model.get_variable_value("x") - 10.0) < 1e-6

    def test_options_persist_after_clear(self):
        """Test options persist after clear."""
        options = SolverOptions(duality_gap=0.02, time_limit=duration(seconds=45))
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        model.add_continuous_variable("x", 0, 5)
        model.solve()
        model.clear()

        assert model.options.duality_gap == 0.02
        assert model.options.time_limit == duration(seconds=45)
        assert len(model.variables) == 0


class TestSolverOptionsParameterPassing:
    """Tests that verify options are actually passed to the solver via parameter builders."""

    def test_presolve_disabled_passed_to_solver(self):
        """Test that presolve=False is passed to solver."""
        options = SolverOptions(presolve=False)
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        # Mock the parameter builder
        mock_builder = MagicMock()
        model._parameter_builder = mock_builder

        x = model.add_continuous_variable("x", 0, 10)
        model.set_direction("maximize")
        model.set_objective(x)
        model.solve()

        # Verify apply_options was called with the correct options
        mock_builder.apply_options.assert_called_once()
        call_options = mock_builder.apply_options.call_args[0][0]
        assert call_options.presolve is False

    def test_duality_gap_passed_to_solver(self):
        """Test that duality_gap is passed to solver."""
        options = SolverOptions(duality_gap=0.05)
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        # Mock the parameter builder
        mock_builder = MagicMock()
        model._parameter_builder = mock_builder

        x = model.add_continuous_variable("x", 0, 10)
        model.set_direction("maximize")
        model.set_objective(x)
        model.solve()

        # Verify apply_options was called with the correct options
        mock_builder.apply_options.assert_called_once()
        call_options = mock_builder.apply_options.call_args[0][0]
        assert call_options.duality_gap == 0.05

    def test_time_limit_passed_to_solver(self):
        """Test that time_limit is passed to solver."""
        options = SolverOptions(time_limit=duration(seconds=30))
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        # Mock the parameter builder
        mock_builder = MagicMock()
        model._parameter_builder = mock_builder

        x = model.add_continuous_variable("x", 0, 10)
        model.set_direction("maximize")
        model.set_objective(x)
        model.solve()

        # Verify apply_options was called with the correct options
        mock_builder.apply_options.assert_called_once()
        call_options = mock_builder.apply_options.call_args[0][0]
        assert call_options.time_limit == duration(seconds=30)

    def test_all_options_passed_to_solver(self):
        """Test that all options are passed to solver together."""
        options = SolverOptions(presolve=False, duality_gap=0.02, time_limit=duration(seconds=60))
        model = OptimisationModel(solver_name=SolverEnum.GLOP, options=options)

        # Mock the parameter builder
        mock_builder = MagicMock()
        model._parameter_builder = mock_builder

        x = model.add_continuous_variable("x", 0, 10)
        model.set_direction("maximize")
        model.set_objective(x)
        model.solve()

        # Verify apply_options was called with all options
        mock_builder.apply_options.assert_called_once()
        call_options = mock_builder.apply_options.call_args[0][0]
        assert call_options.presolve is False
        assert call_options.duality_gap == 0.02
        assert call_options.time_limit == duration(seconds=60)

    @requires_xpress
    def test_xpress_uses_xpress_builder(self):
        """Test that XPRESS solver uses XPRESSParameterBuilder."""
        from atlas.solver.solver_interface import XPRESSParameterBuilder

        model = OptimisationModel(solver_name=SolverEnum.XPRESS)
        assert isinstance(model._parameter_builder, XPRESSParameterBuilder)

    def test_generic_solver_uses_generic_builder(self):
        """Test that generic solvers use GenericParameterBuilder."""
        from atlas.solver.solver_interface import GenericParameterBuilder

        model = OptimisationModel(solver_name=SolverEnum.GLOP)
        assert isinstance(model._parameter_builder, GenericParameterBuilder)

    def test_scip_uses_scip_builder(self):
        """Test that SCIP solver uses SCIPParameterBuilder."""
        from atlas.solver.solver_interface import SCIPParameterBuilder

        model = OptimisationModel(solver_name=SolverEnum.SCIP)
        assert isinstance(model._parameter_builder, SCIPParameterBuilder)

    def test_scip_parameter_format(self):
        """Test that SCIP parameters are formatted correctly."""
        from unittest.mock import patch

        from atlas.solver.solver_interface import SCIPParameterBuilder

        options = SolverOptions(presolve=False, duality_gap=0.0001)
        model = OptimisationModel(solver_name=SolverEnum.SCIP, options=options)

        # Patch SetSolverSpecificParametersAsString to capture the parameter string
        with patch.object(model._solver, "SetSolverSpecificParametersAsString") as mock_set_params:
            mock_set_params.return_value = True

            x = model.add_continuous_variable("x", 0, 10)
            model.set_direction("maximize")
            model.set_objective(x)
            model.solve()

            # Verify the parameter string format
            mock_set_params.assert_called_once()
            param_string = mock_set_params.call_args[0][0]

            # SCIP expects newline-separated parameters in the format "parameter/name = value"
            assert "presolving/maxrounds = 0" in param_string
            assert "limits/gap = 0.0001" in param_string
            # Parameters should be separated by newlines, not spaces
            assert "\n" in param_string
