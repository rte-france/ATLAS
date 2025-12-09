"""
Pytest tests for the OptimisationModel with expression syntax.

Run with: pytest test_optimisation_model.py -v
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from pendulum import duration

from atlas.enum import SolverStatus
from atlas.solver.solver_interface import OptimisationModel, SolutionInfo


class TestOptimisationModel:
    """Test suite for OptimisationModel class."""

    @pytest.fixture
    def mock_solver(self):
        """Mock OR-Tools solver for testing."""
        mock_solver = MagicMock()
        mock_solver.NumVar.return_value = MagicMock()
        mock_solver.IntVar.return_value = MagicMock()
        mock_solver.BoolVar.return_value = MagicMock()
        mock_solver.Add.return_value = None
        mock_solver.Minimize.return_value = None
        mock_solver.Maximize.return_value = None
        mock_solver.Solve.return_value = 0  # OPTIMAL
        mock_solver.Objective.return_value.Value.return_value = 100.0
        mock_solver.iterations.return_value = 10
        mock_solver.LookupVariable.return_value.solution_value.return_value = 5.0
        mock_solver.ExportModelAsLpFormat.return_value = "LP FORMAT CONTENT"
        mock_solver.SetTimeLimit.return_value = None
        return mock_solver

    @pytest.fixture
    def model(self, mock_solver):
        """Create a test OptimisationModel instance."""
        with patch("ortools.linear_solver.pywraplp.Solver.CreateSolver", return_value=mock_solver):
            return OptimisationModel("GLOP", "test_model")

    def test_model_initialization_with_name(self, mock_solver):
        """Test model initialization with name."""
        with patch("ortools.linear_solver.pywraplp.Solver.CreateSolver", return_value=mock_solver):
            model = OptimisationModel("GLOP", "test_model")
            assert model.name == "test_model"
            assert model.solver_name == "GLOP"
            assert model.solver is mock_solver

    def test_model_initialization_without_name(self, mock_solver):
        """Test model initialization without name."""
        with patch("ortools.linear_solver.pywraplp.Solver.CreateSolver", return_value=mock_solver):
            model = OptimisationModel("SCIP")
            assert model.name is None
            assert model.solver_name == "SCIP"

    def test_solver_creation_failure(self):
        """Test handling of solver creation failure."""
        with patch("ortools.linear_solver.pywraplp.Solver.CreateSolver", return_value=None):
            with pytest.raises(ValueError, match="'INVALID_SOLVER' is not a valid SolverEnum"):
                OptimisationModel("INVALID_SOLVER")

    def test_add_continuous_variable(self, model, mock_solver):
        """Test adding continuous variables."""
        # Test normal case
        var = model.add_continuous_variable("x", 0, 10)
        assert "x" in model.variables
        mock_solver.NumVar.assert_called_with(0, 10, "x")
        assert var is mock_solver.NumVar.return_value

        # Test with default bounds
        model.add_continuous_variable("y")
        mock_solver.NumVar.assert_called_with(float("-inf"), float("inf"), "y")

        # Test duplicate variable
        with pytest.raises(ValueError, match="Variable 'x' already exists"):
            model.add_continuous_variable("x", 0, 5)

    def test_add_integer_variable(self, model, mock_solver):
        """Test adding integer variables."""
        model.add_integer_variable("y", -5, 15)
        assert "y" in model.variables
        mock_solver.IntVar.assert_called_with(-5, 15, "y")

        # Test duplicate variable
        with pytest.raises(ValueError, match="Variable 'y' already exists"):
            model.add_integer_variable("y")

    def test_add_boolean_variable(self, model, mock_solver):
        """Test adding boolean variables."""
        model.add_boolean_variable("z")
        assert "z" in model.variables
        mock_solver.BoolVar.assert_called_with("z")

        # Test duplicate variable
        with pytest.raises(ValueError, match="Variable 'z' already exists"):
            model.add_boolean_variable("z")

    def test_get_variable(self, model, mock_solver):
        """Test getting variable objects."""
        # Add a variable first
        model.add_continuous_variable("x", 0, 10)

        # Test getting existing variable
        model.get_variable("x")
        # FIXME following test must be done in order to assert that both variable are the same
        # assert var.index() == retrieved_var.index()
        mock_solver.LookupVariable.assert_called_with("x")

        # Test getting non-existent variable
        with pytest.raises(ValueError, match="Variable 'nonexistent' not found"):
            model.get_variable("nonexistent")

    def test_add_constraint(self, model, mock_solver):
        """Test adding constraints with expressions."""
        mock_expr = MagicMock()

        # Test adding constraint with automatic name
        model.add_constraint(mock_expr)
        expected_name = "constraint_0"
        assert expected_name in model.constraints
        mock_solver.Add.assert_called_with(mock_expr, expected_name)

        # Test adding constraint with custom name
        model.add_constraint(mock_expr, "custom_constraint")
        assert "custom_constraint" in model.constraints
        mock_solver.Add.assert_called_with(mock_expr, "custom_constraint")

        # Test duplicate constraint name
        with pytest.raises(ValueError, match="Constraint 'custom_constraint' already exists"):
            model.add_constraint(mock_expr, "custom_constraint")

    def test_set_direction_maximize(self, model):
        """Test setting direction to maximize."""
        model.set_direction("maximize")
        assert model._objective_direction == "maximize"

    def test_set_direction_minimize(self, model):
        """Test setting direction to minimize."""
        model.set_direction("minimize")
        assert model._objective_direction == "minimize"

    def test_set_direction_immutable(self, model):
        """Test that direction cannot be changed once set (immutable)."""
        # Set direction first time
        model.set_direction("maximize")
        assert model._objective_direction == "maximize"

        # Try to change to minimize - should raise error
        with pytest.raises(ValueError, match="Optimization direction is already set"):
            model.set_direction("minimize")

        # Verify direction hasn't changed
        assert model._objective_direction == "maximize"

    def test_set_direction_same_value_twice(self, model):
        """Test that setting the same direction twice still raises error."""
        model.set_direction("maximize")

        # Even setting the same value should raise error (immutable means immutable)
        with pytest.raises(ValueError, match="Optimization direction is already set"):
            model.set_direction("maximize")

    def test_set_direction_invalid_value(self, model):
        """Test setting invalid direction value."""
        with pytest.raises(ValueError, match="Direction must be 'maximize' or 'minimize'"):
            model.set_direction("invalid")

        # Direction should still be None
        assert model._objective_direction is None

    def test_set_direction_after_clear(self, model):
        """Test that direction can be set again after clearing the model."""
        # Set direction and add objective
        model.set_direction("maximize")
        mock_expr = MagicMock()
        model.add_objective(mock_expr)

        # Clear the model
        model.clear()
        assert model._objective_direction is None

        # Should be able to set direction again after clear
        model.set_direction("minimize")
        assert model._objective_direction == "minimize"

    def test_set_objective_maximize(self, model, mock_solver):
        """Test setting objective with maximize direction."""
        mock_expr = MagicMock()
        model.set_direction("maximize")
        model.set_objective(mock_expr)

        mock_solver.Maximize.assert_called_with(mock_expr)
        assert model._objective is mock_expr
        assert model._objective_direction == "maximize"

    def test_set_objective_minimize(self, model, mock_solver):
        """Test setting objective with minimize direction."""
        mock_expr = MagicMock()
        model.set_direction("minimize")
        model.set_objective(mock_expr)

        mock_solver.Minimize.assert_called_with(mock_expr)
        assert model._objective is mock_expr
        assert model._objective_direction == "minimize"

    def test_set_objective_without_direction(self, model, mock_solver):
        """Test setting objective without first setting direction."""
        mock_expr = MagicMock()
        with pytest.raises(ValueError, match="Optimization direction must be set before setting objective"):
            model.set_objective(mock_expr)

    def test_add_objective_first_call_maximize(self, model, mock_solver):
        """Test first call to add_objective with maximize direction."""
        mock_expr = MagicMock()
        model.set_direction("maximize")
        model.add_objective(mock_expr)

        mock_solver.Maximize.assert_called_with(mock_expr)
        assert model._objective is mock_expr
        assert model._objective_direction == "maximize"

    def test_add_objective_first_call_minimize(self, model, mock_solver):
        """Test first call to add_objective with minimize direction."""
        mock_expr = MagicMock()
        model.set_direction("minimize")
        model.add_objective(mock_expr)

        mock_solver.Minimize.assert_called_with(mock_expr)
        assert model._objective is mock_expr
        assert model._objective_direction == "minimize"

    def test_add_objective_multiple_calls_same_direction(self, model, mock_solver):
        """Test multiple calls to add_objective."""
        mock_expr1 = MagicMock()
        mock_expr2 = MagicMock()
        mock_expr3 = MagicMock()

        # Configure mock addition to return new mock objects
        mock_expr1.__add__ = MagicMock(return_value=MagicMock())
        mock_expr1.__add__.return_value.__add__ = MagicMock(return_value=MagicMock())

        # Set direction first
        model.set_direction("maximize")

        # First call
        model.add_objective(mock_expr1)
        assert model._objective is mock_expr1
        assert model._objective_direction == "maximize"

        # Second call - should add to existing objective
        model.add_objective(mock_expr2)
        mock_expr1.__add__.assert_called_with(mock_expr2)
        assert model._objective_direction == "maximize"

        # Third call - should add to existing combined objective
        model.add_objective(mock_expr3)
        assert model._objective_direction == "maximize"

    def test_add_objective_without_direction(self, model, mock_solver):
        """Test add_objective without first setting direction."""
        mock_expr1 = MagicMock()

        # Should raise error when direction is not set
        with pytest.raises(
            ValueError,
            match="Optimization direction must be set before adding objective terms",
        ):
            model.add_objective(mock_expr1)

    def test_add_objective_after_set_objective(self, model, mock_solver):
        """Test add_objective after using set_objective."""
        mock_expr1 = MagicMock()
        mock_expr2 = MagicMock()

        # Configure mock addition
        mock_expr1.__add__ = MagicMock(return_value=MagicMock())

        # First set direction and objective
        model.set_direction("maximize")
        model.set_objective(mock_expr1)

        # Then add to it
        model.add_objective(mock_expr2)
        mock_expr1.__add__.assert_called_with(mock_expr2)

    def test_set_objective_after_add_objective(self, model, mock_solver):
        """Test set_objective after using add_objective (should replace)."""
        mock_expr1 = MagicMock()
        mock_expr2 = MagicMock()

        # First set direction and add objective
        model.set_direction("maximize")
        model.add_objective(mock_expr1)
        assert model._objective is mock_expr1

        # Then set objective (should replace, but direction stays the same)
        model.set_objective(mock_expr2)
        assert model._objective is mock_expr2
        assert model._objective_direction == "maximize"
        mock_solver.Maximize.assert_called_with(mock_expr2)

    def test_solve_without_time_limit(self, model, mock_solver):
        """Test solving without time limit."""
        solution = model.solve()

        assert isinstance(solution, SolutionInfo)
        assert solution.status == SolverStatus.OPTIMAL
        assert solution.objective_value == 100.0
        assert solution.num_iterations == 10
        assert solution.solve_time is not None

        mock_solver.Solve.assert_called_once()
        mock_solver.SetTimeLimit.assert_not_called()

    def test_solve_with_time_limit(self, model, mock_solver):
        """Test solving with time limit via SolverOptions."""
        from atlas.solver.models import SolverOptions

        model.set_solver_options(SolverOptions(time_limit=duration(seconds=30)))
        model.solve()

        mock_solver.SetTimeLimit.assert_called_with(30000)  # 30.0 * 1000
        mock_solver.Solve.assert_called_once()

    def test_solve_infeasible(self, model, mock_solver):
        """Test solving infeasible problem."""
        # Mock infeasible status
        mock_solver.Solve.return_value = 2  # INFEASIBLE

        solution = model.solve()

        assert solution.status == SolverStatus.INFEASIBLE
        assert solution.objective_value is None

    def test_get_variable_value_after_solving(self, model, mock_solver):
        """Test getting variable values after solving."""
        # Add variable and solve first
        model.add_continuous_variable("x", 0, 10)
        model.solve()

        value = model.get_variable_value("x")
        assert value == 5.0
        mock_solver.LookupVariable.assert_called_with("x")

    def test_get_variable_value_before_solving(self, model):
        """Test getting variable values before solving."""
        model.add_continuous_variable("x", 0, 10)

        with pytest.raises(RuntimeError, match="Optimisation model has not been solved yet"):
            model.get_variable_value("x")

    def test_get_variable_value_nonexistent_variable(self, model, mock_solver):
        """Test getting value of non-existent variable."""
        # Solve first to have solution info
        model.solve()

        with pytest.raises(ValueError, match="Variable 'nonexistent' not found in solution"):
            model.get_variable_value("nonexistent")

    def test_get_constraint(self, model, mock_solver):
        """Test getting constraint objects."""
        # Add a constraint first
        mock_expr = MagicMock()
        model.add_constraint(mock_expr, "test_constraint")

        # Test getting existing constraint
        model.get_constraint("test_constraint")
        mock_solver.LookupConstraint.assert_called_with("test_constraint")

        # Test getting non-existent constraint
        with pytest.raises(ValueError, match="Constraint 'nonexistent' not found"):
            model.get_constraint("nonexistent")

    def test_get_constraint_bounds_basic(self, model, mock_solver):
        """Test getting constraint bounds for a constraint."""
        # Setup mock constraint
        mock_constraint = MagicMock()
        mock_constraint.lb.return_value = 5.0
        mock_constraint.ub.return_value = 10.0
        mock_solver.LookupConstraint.return_value = mock_constraint

        # Add constraint
        model._constraints_name.add("test_constraint")

        # Get bounds
        bounds = model.get_constraint_bounds("test_constraint")

        assert bounds.lower_bound == 5.0
        assert bounds.upper_bound == 10.0
        mock_solver.LookupConstraint.assert_called_with("test_constraint")

    def test_get_constraint_bounds_infinity(self, model, mock_solver):
        """Test getting constraint bounds with infinite bounds."""
        # Setup mock constraint with infinite bounds
        mock_constraint = MagicMock()
        mock_constraint.lb.return_value = float("-inf")
        mock_constraint.ub.return_value = float("inf")
        mock_solver.LookupConstraint.return_value = mock_constraint

        model._constraints_name.add("unbounded_constraint")

        bounds = model.get_constraint_bounds("unbounded_constraint")

        assert bounds.lower_bound == float("-inf")
        assert bounds.upper_bound == float("inf")

    def test_get_constraint_bounds_upper_only(self, model, mock_solver):
        """Test getting constraint bounds with only upper bound."""
        mock_constraint = MagicMock()
        mock_constraint.lb.return_value = float("-inf")
        mock_constraint.ub.return_value = 100.0
        mock_solver.LookupConstraint.return_value = mock_constraint

        model._constraints_name.add("upper_bound_constraint")

        bounds = model.get_constraint_bounds("upper_bound_constraint")

        assert bounds.lower_bound == float("-inf")
        assert bounds.upper_bound == 100.0

    def test_get_constraint_bounds_lower_only(self, model, mock_solver):
        """Test getting constraint bounds with only lower bound."""
        mock_constraint = MagicMock()
        mock_constraint.lb.return_value = 0.0
        mock_constraint.ub.return_value = float("inf")
        mock_solver.LookupConstraint.return_value = mock_constraint

        model._constraints_name.add("lower_bound_constraint")

        bounds = model.get_constraint_bounds("lower_bound_constraint")

        assert bounds.lower_bound == 0.0
        assert bounds.upper_bound == float("inf")

    def test_get_constraint_bounds_equality(self, model, mock_solver):
        """Test getting constraint bounds for equality constraint."""
        mock_constraint = MagicMock()
        mock_constraint.lb.return_value = 5.0
        mock_constraint.ub.return_value = 5.0
        mock_solver.LookupConstraint.return_value = mock_constraint

        model._constraints_name.add("equality_constraint")

        bounds = model.get_constraint_bounds("equality_constraint")

        assert bounds.lower_bound == 5.0
        assert bounds.upper_bound == 5.0

    def test_get_constraint_bounds_negative(self, model, mock_solver):
        """Test getting constraint bounds with negative values."""
        mock_constraint = MagicMock()
        mock_constraint.lb.return_value = -20.0
        mock_constraint.ub.return_value = -5.0
        mock_solver.LookupConstraint.return_value = mock_constraint

        model._constraints_name.add("negative_constraint")

        bounds = model.get_constraint_bounds("negative_constraint")

        assert bounds.lower_bound == -20.0
        assert bounds.upper_bound == -5.0

    def test_get_constraint_bounds_zero(self, model, mock_solver):
        """Test getting constraint bounds with zero values."""
        mock_constraint = MagicMock()
        mock_constraint.lb.return_value = 0.0
        mock_constraint.ub.return_value = 0.0
        mock_solver.LookupConstraint.return_value = mock_constraint

        model._constraints_name.add("zero_constraint")

        bounds = model.get_constraint_bounds("zero_constraint")

        assert bounds.lower_bound == 0.0
        assert bounds.upper_bound == 0.0

    def test_get_constraint_bounds_nonexistent(self, model, mock_solver):
        """Test getting bounds for non-existent constraint."""
        with pytest.raises(ValueError, match="Constraint 'nonexistent' not found"):
            model.get_constraint_bounds("nonexistent")

    def test_get_constraint_slack_value_not_solved(self, model):
        model._constraints_name.add("c1")

        with pytest.raises(RuntimeError):
            model.get_constraint_slack_value("c1")

    def test_get_constraint_slack_value_ub_only(self, model, mock_solver):
        mock_constraint = MagicMock()
        mock_constraint.ub.return_value = 11
        mock_constraint.lb.return_value = -float("inf")
        mock_constraint.GetCoefficient.side_effect = lambda var: 1.0

        mock_var = MagicMock()
        mock_var.solution_value.return_value = 5.0

        mock_solver.variables.return_value = [mock_var]
        mock_solver.LookupConstraint.return_value = mock_constraint

        model._constraints_name.add("c_upper")
        model._solution_info = MagicMock()

        slack = model.get_constraint_slack_value("c_upper")
        assert pytest.approx(5.0 - 11.0 + slack, 1e-8) == 0.0

    def test_get_constraint_slack_value_lb_only(self, model, mock_solver):
        mock_constraint = MagicMock()
        mock_constraint.ub.return_value = float("inf")
        mock_constraint.lb.return_value = 2.0
        mock_constraint.GetCoefficient.side_effect = lambda var: 1.0

        mock_var = MagicMock()
        mock_var.solution_value.return_value = 5.0

        mock_solver.variables.return_value = [mock_var]
        mock_solver.LookupConstraint.return_value = mock_constraint

        model._constraints_name.add("c_lower")
        model._solution_info = MagicMock()

        slack = model.get_constraint_slack_value("c_lower")
        assert pytest.approx(5.0 - 2.0 + slack, 1e-8) == 0.0

    def test_export_model(self, model, mock_solver):
        """Test exporting model to file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            temp_filename = f.name

        try:
            model.export_model(temp_filename)

            mock_solver.ExportModelAsLpFormat.assert_called_with(False)

            # Check file was written
            assert os.path.exists(temp_filename)
            with open(temp_filename) as f:
                content = f.read()
                assert content == "LP FORMAT CONTENT"
        finally:
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)

    def test_clear(self, model):
        """Test clearing the model."""
        # Add some data first
        model.add_continuous_variable("x", 0, 10)
        model.add_constraint(MagicMock(), "test_constraint")
        model.set_direction("maximize")
        model.set_objective(MagicMock())
        model.solve()  # Create solution info

        # Verify data exists
        assert len(model.variables) > 0
        assert len(model.constraints) > 0
        assert model.solution_info is not None
        assert model._objective is not None
        assert model._objective_direction is not None

        # Clear and verify
        model.clear()
        assert len(model.variables) == 0
        assert len(model.constraints) == 0
        assert model.solution_info is None
        assert model._objective is None
        assert model._objective_direction is None

    def test_model_properties(self, model):
        """Test model properties."""
        # Test empty model
        assert len(model.variables) == 0
        assert len(model.constraints) == 0
        assert model.solution_info is None

        # Add some data and test
        model.add_continuous_variable("x")
        model.add_continuous_variable("y")
        assert len(model.variables) == 2

        model.add_constraint(MagicMock(), "c1")
        model.add_constraint(MagicMock(), "c2")
        assert len(model.constraints) == 2

        model.set_direction("maximize")
        model.set_objective(MagicMock())

    def test_model_repr(self, model):
        """Test string representation of the model."""
        expected = "OptimisationModel(name=test_model,solver=GLOP)"
        assert repr(model) == expected

        # Test without name
        with patch("ortools.linear_solver.pywraplp.Solver.CreateSolver"):
            model_no_name = OptimisationModel("SCIP")
            expected_no_name = "OptimisationModel(name=None,solver=SCIP)"
            assert repr(model_no_name) == expected_no_name


class TestIntegrationScenarios:
    """Integration tests for common optimization scenarios."""

    @pytest.fixture
    def mock_solver_setup(self):
        """Setup a mock solver for integration tests."""
        mock_solver = MagicMock()
        mock_solver.NumVar.return_value = MagicMock()
        mock_solver.IntVar.return_value = MagicMock()
        mock_solver.BoolVar.return_value = MagicMock()
        mock_solver.Add.return_value = None
        mock_solver.Maximize.return_value = None
        mock_solver.Minimize.return_value = None
        mock_solver.Solve.return_value = 0  # OPTIMAL
        mock_solver.Objective.return_value.Value.return_value = 150.0
        mock_solver.iterations.return_value = 5
        mock_solver.LookupVariable.return_value.solution_value.return_value = 2.5
        mock_solver.ExportModelAsLpFormat.return_value = (
            "Minimize\n obj: x + y\nSubject To\n constraint: x + y <= 10\nEnd"
        )
        return mock_solver

    @pytest.fixture
    def integration_model(self, mock_solver_setup):
        """Create a model for integration testing."""
        with patch("ortools.linear_solver.pywraplp.Solver.CreateSolver", return_value=mock_solver_setup):
            return OptimisationModel("GLOP", "integration_test")

    def test_simple_linear_program(self, integration_model):
        """Test a simple linear programming problem."""
        # Variables: x, y >= 0
        x = integration_model.add_continuous_variable("x", 0, 10)
        y = integration_model.add_continuous_variable("y", 0, 10)

        # Constraints:
        # x + y <= 8
        # 2x + y <= 10
        # x, y >= 0 (handled by bounds)
        integration_model.add_constraint(x + y, "capacity")  # Mock expression
        integration_model.add_constraint(2 * x + y, "resource")  # Mock expression

        # Objective: maximize 3x + 2y
        integration_model.set_direction("maximize")
        integration_model.set_objective(3 * x + 2 * y)

        # Solve
        solution = integration_model.solve()

        assert solution.status == SolverStatus.OPTIMAL
        assert solution.objective_value == 150.0
        assert len(integration_model.variables) == 2
        assert len(integration_model.constraints) == 2

        # Get variable values
        x_value = integration_model.get_variable_value("x")
        y_value = integration_model.get_variable_value("y")
        assert x_value == 2.5
        assert y_value == 2.5

    def test_incremental_objective_building(self, integration_model):
        """Test building objective incrementally with add_objective."""
        # Variables
        integration_model.add_continuous_variable("x", 0, 10)
        integration_model.add_continuous_variable("y", 0, 10)
        integration_model.add_continuous_variable("z", 0, 10)

        # Mock expression addition
        mock_expr1 = MagicMock()
        mock_expr2 = MagicMock()
        mock_expr3 = MagicMock()
        mock_combined1 = MagicMock()
        mock_combined2 = MagicMock()

        mock_expr1.__add__ = MagicMock(return_value=mock_combined1)
        mock_combined1.__add__ = MagicMock(return_value=mock_combined2)

        # Set direction first
        integration_model.set_direction("maximize")

        # Build objective incrementally
        integration_model.add_objective(mock_expr1)  # Start with first term
        integration_model.add_objective(mock_expr2)  # Add second term
        integration_model.add_objective(mock_expr3)  # Add third term

        # Verify the expressions were combined
        mock_expr1.__add__.assert_called_with(mock_expr2)
        mock_combined1.__add__.assert_called_with(mock_expr3)

        # Solve
        solution = integration_model.solve()
        assert solution.status == SolverStatus.OPTIMAL

    def test_mixed_integer_program(self, integration_model):
        """Test a mixed integer programming problem."""
        # Continuous and integer variables
        x = integration_model.add_continuous_variable("x", 0, 100)
        y = integration_model.add_integer_variable("y", 0, 50)
        z = integration_model.add_boolean_variable("z")

        # Constraints with mixed variables
        integration_model.add_constraint(x + 5 * y, "capacity")
        integration_model.add_constraint(x - 10 * z, "activation")
        integration_model.add_constraint(y - 20 * z, "linking")

        # Objective
        integration_model.set_direction("maximize")
        integration_model.set_objective(2 * x + 10 * y + 50 * z)

        solution = integration_model.solve()

        assert solution.status == SolverStatus.OPTIMAL
        assert len(integration_model.variables) == 3
        assert len(integration_model.constraints) == 3

    def test_workflow_with_modifications(self, integration_model):
        """Test a workflow with model modifications."""
        # Initial setup
        x = integration_model.add_continuous_variable("x", 0, 10)
        y = integration_model.add_continuous_variable("y", 0, 10)

        integration_model.add_constraint(x + y, "initial_constraint")
        integration_model.set_direction("maximize")
        integration_model.set_objective(x + y)

        # Solve initial model
        solution1 = integration_model.solve()
        assert solution1.status == SolverStatus.OPTIMAL

        # Add more variables and constraints
        z = integration_model.add_boolean_variable("z")
        integration_model.add_constraint(x + z, "additional_constraint")

        # Solve modified model
        solution2 = integration_model.solve()
        assert solution2.status == SolverStatus.OPTIMAL
        assert len(integration_model.variables) == 3
        assert len(integration_model.constraints) == 2

    def test_add_objective_workflow(self, integration_model):
        """Test workflow using add_objective method."""
        # Variables
        x = integration_model.add_continuous_variable("x", 0, 10)
        y = integration_model.add_continuous_variable("y", 0, 10)
        z = integration_model.add_continuous_variable("z", 0, 10)

        # Set direction first
        integration_model.set_direction("maximize")

        # Build objective step by step
        integration_model.add_objective(x)  # profit from x
        integration_model.add_objective(2 * y)  # double profit from y
        integration_model.add_objective(-0.5 * z)  # cost of z

        # Add constraints
        integration_model.add_constraint(x + y + z, "resource_limit")

        # Solve
        solution = integration_model.solve()
        assert solution.status == SolverStatus.OPTIMAL
        assert integration_model._objective_direction == "maximize"

    def test_error_handling_workflow(self, integration_model):
        """Test error handling in a typical workflow."""
        # Add variables
        x = integration_model.add_continuous_variable("x")

        # Try to add duplicate variable
        with pytest.raises(ValueError, match="Variable 'x' already exists"):
            integration_model.add_continuous_variable("x")

        # Add constraint and try duplicate
        integration_model.add_constraint(x, "test_constraint")
        with pytest.raises(ValueError, match="Constraint 'test_constraint' already exists"):
            integration_model.add_constraint(x, "test_constraint")

        # Try to get non-existent variable
        with pytest.raises(ValueError, match="Variable 'nonexistent' not found"):
            integration_model.get_variable("nonexistent")

        # Try to get variable value before solving
        with pytest.raises(RuntimeError, match="Optimisation model has not been solved yet"):
            integration_model.get_variable_value("x")

        # Test add_objective without direction
        with pytest.raises(
            ValueError,
            match="Optimization direction must be set before adding objective terms",
        ):
            integration_model.add_objective(x)

        # Test setting direction twice
        integration_model.set_direction("maximize")
        with pytest.raises(ValueError, match="Optimization direction is already set"):
            integration_model.set_direction("minimize")

    def test_model_export_and_clear_workflow(self, integration_model):
        """Test export and clear in a workflow."""
        # Build model
        x = integration_model.add_continuous_variable("x")
        y = integration_model.add_continuous_variable("y")
        integration_model.add_constraint(x + y, "sum_constraint")
        integration_model.set_direction("maximize")
        integration_model.add_objective(x)
        integration_model.add_objective(y)

        # Solve
        solution = integration_model.solve()
        assert solution.status == SolverStatus.OPTIMAL

        # Export
        with tempfile.NamedTemporaryFile(suffix=".lp", delete=False) as f:
            temp_file = f.name

        try:
            integration_model.export_model(temp_file)
            assert os.path.exists(temp_file)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

        # Clear and verify
        integration_model.clear()
        assert len(integration_model.variables) == 0
        assert len(integration_model.constraints) == 0
        assert integration_model.solution_info is None
        assert integration_model._objective is None
        assert integration_model._objective_direction is None
