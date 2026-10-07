"""
Tests for the solve-status guard on the solution accessors of OptimisationModel.

OR-Tools returns its default 0.0 for every variable of a model that could not be solved, so
reading the solution of a failed solve used to produce plausible-looking but meaningless results.

Run with: pytest tests/test_unit/test_solver/test_solution_guard.py -v
"""

from io import StringIO

import pendulum
import pytest
from loguru import logger as loguru_logger

from atlas.custom_errors import ModelNotSolvedError, SolverError, UnsuccessfulSolveError
from atlas.enums import SolverEnum, SolverStatus
from atlas.solver.models import SolutionInfo
from atlas.solver.solver_interface import OptimisationModel


def build_infeasible_model(name: str | None = "infeasible_test") -> OptimisationModel:
    """Build a model with contradictory bounds: ``x >= 5`` while ``x <= 1``.

    :param name: Name given to the optimisation model
    :type name: str | None
    :return: An unsolved model whose solve can only fail
    :rtype: OptimisationModel
    """
    model = OptimisationModel(solver_name=SolverEnum.GLOP, name=name)
    x = model.add_continuous_variable("x", 0, 1)
    model.add_constraint(x >= 5, "impossible")
    model.set_direction("maximize")
    model.set_objective(x)
    return model


def build_feasible_model() -> OptimisationModel:
    """Build a small model with a single optimum at ``x = 10``.

    :return: An unsolved model that solves to OPTIMAL
    :rtype: OptimisationModel
    """
    model = OptimisationModel(solver_name=SolverEnum.GLOP, name="feasible_test")
    x = model.add_continuous_variable("x", 0, 10)
    model.add_constraint(x <= 10, "capacity")
    model.set_direction("maximize")
    model.set_objective(x)
    return model


class TestSolutionInfoIsSuccessful:
    """Test suite for SolutionInfo.is_successful."""

    @pytest.mark.parametrize("status", [SolverStatus.OPTIMAL, SolverStatus.FEASIBLE])
    def test_successful_statuses(self, status):
        assert SolutionInfo(status=status).is_successful

    @pytest.mark.parametrize(
        "status",
        [
            SolverStatus.INFEASIBLE,
            SolverStatus.UNBOUNDED,
            SolverStatus.ABNORMAL,
            SolverStatus.NOT_SOLVED,
            SolverStatus.MODEL_INVALID,
        ],
    )
    def test_unsuccessful_statuses(self, status):
        assert not SolutionInfo(status=status).is_successful


class TestCheckSolution:
    """Test suite for OptimisationModel.require_solution and has_solution."""

    def test_has_solution_is_false_before_solving(self):
        model = build_feasible_model()

        assert model.has_solution is False

    def test_has_solution_is_true_after_a_successful_solve(self):
        model = build_feasible_model()
        model.solve()

        assert model.has_solution is True

    def test_has_solution_is_false_after_a_failed_solve(self):
        model = build_infeasible_model()
        model.solve()

        assert model.has_solution is False

    def test_require_solution_raises_before_solving(self):
        model = build_feasible_model()

        with pytest.raises(ModelNotSolvedError, match="has not been solved yet"):
            model.require_solution()

    def test_require_solution_passes_on_a_successful_solve(self):
        model = build_feasible_model()
        model.solve()

        model.require_solution()

    def test_require_solution_raises_on_a_failed_solve(self):
        model = build_infeasible_model()
        model.solve()

        with pytest.raises(UnsuccessfulSolveError) as excinfo:
            model.require_solution()

        assert excinfo.value.status == SolverStatus.INFEASIBLE
        assert "infeasible_test" in str(excinfo.value)
        assert "INFEASIBLE" in str(excinfo.value)

    def test_unsuccessful_solve_error_is_a_solver_error(self):
        model = build_infeasible_model(name=None)
        model.solve()

        with pytest.raises(SolverError):
            model.require_solution()

    def test_failed_solve_is_logged_as_an_error(self):
        model = build_infeasible_model()
        captured = StringIO()
        sink_id = loguru_logger.add(captured, level="ERROR", format="{level} | {message}")

        try:
            model.solve()
        finally:
            loguru_logger.remove(sink_id)

        assert "ERROR | infeasible_test optimisation finished" in captured.getvalue()
        assert "INFEASIBLE" in captured.getvalue()


class TestSolutionAccessorsGuard:
    """Test suite for the guard on the accessors reading a solution."""

    def test_get_variable_value_raises_instead_of_returning_zero(self):
        model = build_infeasible_model()
        model.solve()

        # Before the guard, this returned OR-Tools' default 0.0 and the caller carried on.
        with pytest.raises(UnsuccessfulSolveError):
            model.get_variable_value("x")

    def test_get_constraint_slack_value_raises_instead_of_returning_zero(self):
        model = build_infeasible_model()
        model.solve()

        with pytest.raises(UnsuccessfulSolveError):
            model.get_constraint_slack_value("impossible")

    def test_model_solution_raises_instead_of_returning_zeros(self):
        model = build_infeasible_model()
        model.add_temporal_variable("power", [pendulum.datetime(2025, 1, 1)], upper_bound=1)
        model.solve()

        with pytest.raises(UnsuccessfulSolveError):
            model.solution()

    @pytest.mark.parametrize(
        "read",
        [
            lambda power, t: power.solution_value(t),
            lambda power, t: power.solution(),
            lambda power, t: power.solution_values(),
        ],
        ids=["solution_value", "solution", "solution_values"],
    )
    def test_temporal_variable_raises_instead_of_returning_zeros(self, read):
        model = build_infeasible_model()
        t = pendulum.datetime(2025, 1, 1)
        power = model.add_temporal_variable("power", [t], upper_bound=1)
        model.solve()

        with pytest.raises(UnsuccessfulSolveError):
            read(power, t)

    def test_accessors_work_on_a_solved_model(self):
        model = build_feasible_model()
        model.solve()

        assert model.get_variable_value("x") == pytest.approx(10.0)
        assert model.get_constraint_slack_value("capacity") == pytest.approx(0.0)

    def test_get_variable_stays_usable_after_a_failed_solve(self):
        """A failed attempt is relaxed and re-solved (pricing does this twice), so building the
        next attempt must still be able to reach the variable objects."""
        model = build_infeasible_model()
        model.solve()

        variable = model.get_variable("x")

        assert variable is not None
        model.add_constraint(variable <= 1, "relaxed")
        model.deactivate_constraint("impossible")
        model.solve()

        assert model.has_solution is True
        assert model.get_variable_value("x") == pytest.approx(1.0)
