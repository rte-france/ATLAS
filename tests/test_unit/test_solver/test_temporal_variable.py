"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pickle
import re
from unittest.mock import patch

import pendulum
import pytest

from atlas.enums import SolverStatus, VariableType
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.solver.solver_interface import OptimisationModel
from atlas.solver.temporal_variable import TemporalVariable

START = pendulum.datetime(2025, 1, 1)
TIMESTEP = pendulum.duration(hours=1)
TIMES = [START + k * TIMESTEP for k in range(3)]


@pytest.fixture
def model() -> OptimisationModel:
    return OptimisationModel("SCIP", "test_model")


class TestDeclaration:
    def test_starts_empty(self, model):
        var = model.add_temporal_variable("power")

        assert var.name == "power"
        assert var.variable_type == VariableType.CONTINUOUS
        assert len(var) == 0
        assert var.times == []
        assert model.variables == set()

    def test_times_creates_variables_at_declaration(self, model):
        var = model.add_temporal_variable("power", times=TIMES)

        assert var.model_times == TIMES
        assert model.variables == {f"power_{t}" for t in TIMES}

    @pytest.mark.parametrize("bounds", [{"lower_bound": 0}, {"upper_bound": 1}])
    def test_boolean_rejects_bounds(self, model, bounds):
        with pytest.raises(ValueError, match="does not accept bounds"):
            model.add_temporal_variable("on", variable_type=VariableType.BOOLEAN, **bounds)


class TestAdd:
    def test_add_returns_named_solver_variable(self, model):
        var = model.add_temporal_variable("power")

        created = var.add(START)

        assert created.name() == f"power_{START}"
        assert var[START] is created
        assert model.get_variable(f"power_{START}").index() == created.index()

    def test_constant_bounds(self, model):
        var = model.add_temporal_variable("power", lower_bound=-5, upper_bound=10)

        created = var.add(START)

        assert (created.lb(), created.ub()) == (-5, 10)

    def test_time_dependent_bounds_are_evaluated_at_t(self, model):
        max_power = {t: 10.0 * (k + 1) for k, t in enumerate(TIMES)}
        var = model.add_temporal_variable("power", lower_bound=0, upper_bound=max_power.__getitem__)

        var.add_all(TIMES)

        assert [var[t].ub() for t in TIMES] == [10.0, 20.0, 30.0]

    def test_single_add_evaluates_time_dependent_bounds_at_t(self, model):
        var = model.add_temporal_variable("power", lower_bound=lambda t: -t.hour, upper_bound=lambda t: 10.0 * t.hour)

        created = var.add(TIMES[2])

        assert (created.lb(), created.ub()) == (-2, 20.0)

    def test_default_bounds_follow_model_defaults(self, model):
        continuous = model.add_temporal_variable("power").add(START)
        integer = model.add_temporal_variable("units", variable_type=VariableType.INTEGER).add(START)

        assert (continuous.lb(), continuous.ub()) == (float("-inf"), float("inf"))
        assert (integer.lb(), integer.ub()) == (0, float("inf"))

    @pytest.mark.parametrize(
        ("variable_type", "is_integer"),
        [(VariableType.CONTINUOUS, False), (VariableType.INTEGER, True), (VariableType.BOOLEAN, True)],
    )
    def test_variable_type(self, model, variable_type, is_integer):
        created = model.add_temporal_variable("x", variable_type=variable_type).add(START)

        assert created.integer() is is_integer

    def test_boolean_is_binary(self, model):
        created = model.add_temporal_variable("on", variable_type=VariableType.BOOLEAN).add(START)

        assert (created.lb(), created.ub()) == (0, 1)

    def test_add_twice_raises(self, model):
        var = model.add_temporal_variable("power")
        var.add(START)

        with pytest.raises(ValueError, match="already holds a solver variable"):
            var.add(START)

    def test_add_on_fixed_raises(self, model):
        var = model.add_temporal_variable("power")
        var.fix(START, 1.0)

        with pytest.raises(ValueError, match="already holds a fixed value"):
            var.add(START)


class TestTimeseriesBounds:
    @pytest.fixture(params=["eager", "lazy"])
    def max_power(self, request):
        eager = Timeseries({"time": TIMES, "value": [10.0, 20.0, 30.0]})
        return eager if request.param == "eager" else LazyTimeseries(eager.timeseries.lazy())

    def test_bulk_creation_reads_timeseries_bounds(self, model, max_power):
        var = model.add_temporal_variable("power", TIMES, lower_bound=-max_power, upper_bound=max_power)

        assert [(var[t].lb(), var[t].ub()) for t in TIMES] == [(-10.0, 10.0), (-20.0, 20.0), (-30.0, 30.0)]

    def test_single_add_reads_timeseries_bound(self, model, max_power):
        var = model.add_temporal_variable("power", lower_bound=0, upper_bound=max_power)

        assert var.add(TIMES[1]).ub() == 20.0

    def test_bulk_creation_reads_each_bound_in_one_lookup(self, model):
        max_power = Timeseries({"time": TIMES, "value": [10.0, 20.0, 30.0]})

        with (
            patch.object(Timeseries, "get_values", autospec=True, side_effect=Timeseries.get_values) as get_values,
            patch.object(Timeseries, "get_value", autospec=True) as get_value,
        ):
            model.add_temporal_variable("power", TIMES, lower_bound=max_power, upper_bound=max_power)

        assert get_values.call_count == 2
        get_value.assert_not_called()

    def test_missing_bound_value_raises_before_creating_variables(self, model, max_power):
        with pytest.raises(KeyError, match="not found in the Timeseries"):
            model.add_temporal_variable("power", [*TIMES, TIMES[-1] + TIMESTEP], upper_bound=max_power)

        assert model.variables == set()

    def test_integer_with_timeseries_bound(self, model, max_power):
        var = model.add_temporal_variable("units", TIMES, VariableType.INTEGER, upper_bound=max_power)

        assert [(var[t].lb(), var[t].ub(), var[t].integer()) for t in TIMES] == [
            (0, 10.0, True),
            (0, 20.0, True),
            (0, 30.0, True),
        ]


class TestAddAllChecks:
    def test_duplicates_in_request_raise_before_creating_variables(self, model):
        var = model.add_temporal_variable("power")

        with pytest.raises(ValueError, match="cannot add duplicate timestamps at once"):
            var.add_all([TIMES[0], TIMES[1], TIMES[0]])

        assert len(var) == 0
        assert model.variables == set()

    def test_clash_with_variable_raises_before_creating_variables(self, model):
        var = model.add_temporal_variable("power", [TIMES[1]])

        with pytest.raises(ValueError, match=re.escape(f"already holds a solver variable at {TIMES[1]}")):
            var.add_all(TIMES)

        assert var.model_times == [TIMES[1]]

    def test_clash_with_fixed_value_raises_before_creating_variables(self, model):
        var = model.add_temporal_variable("on", variable_type=VariableType.BOOLEAN)
        var.fix(TIMES[2], 1)

        with pytest.raises(ValueError, match=re.escape(f"already holds a fixed value at {TIMES[2]}")):
            var.add_all(TIMES)

        assert var.model_times == []

    def test_accepts_any_iterable(self, model):
        var = model.add_temporal_variable("power", iter(TIMES))

        assert var.model_times == TIMES

    def test_default_bounds_match_model_defaults(self, model):
        continuous = model.add_temporal_variable("power", TIMES)[TIMES[0]]
        integer = model.add_temporal_variable("units", TIMES, VariableType.INTEGER)[TIMES[0]]
        plain_continuous = model.add_continuous_variable("plain_power")
        plain_integer = model.add_integer_variable("plain_units")

        assert (continuous.lb(), continuous.ub()) == (plain_continuous.lb(), plain_continuous.ub())
        assert (integer.lb(), integer.ub()) == (plain_integer.lb(), plain_integer.ub())


class TestFix:
    def test_fix_returns_value_without_creating_variable(self, model):
        var = model.add_temporal_variable("power")

        var.fix(START, 42.0)

        assert var[START] == 42.0
        assert var.is_fixed(START)
        assert model.variables == set()

    def test_fix_on_variable_raises(self, model):
        var = model.add_temporal_variable("power")
        var.add(START)

        with pytest.raises(ValueError, match="already holds a solver variable"):
            var.fix(START, 1.0)

    def test_fix_twice_raises(self, model):
        var = model.add_temporal_variable("power")
        var.fix(START, 1.0)

        with pytest.raises(ValueError, match="already holds a fixed value"):
            var.fix(START, 2.0)


class TestAccess:
    def test_missing_timestamp_raises_key_error(self, model):
        var = model.add_temporal_variable("power")

        with pytest.raises(KeyError, match=re.escape(f"'power' is not defined at {START}")):
            var[START]

    def test_contains_and_len(self, model):
        var = model.add_temporal_variable("power")
        before = START - TIMESTEP
        var.fix(before, 0.0)
        var.add(START)

        assert before in var
        assert START in var
        assert START + TIMESTEP not in var
        assert len(var) == 2

    def test_times_are_sorted_and_split(self, model):
        var = model.add_temporal_variable("power")
        before = START - TIMESTEP
        var.add_all(reversed(TIMES))
        var.fix(before, 0.0)

        assert var.times == [before, *TIMES]
        assert var.model_times == TIMES
        assert not var.is_fixed(START)

    def test_previous_timestamp_mixes_fixed_and_variable(self, model):
        """A ramp constraint reads the fixed value before the horizon and variables inside it."""
        var = model.add_temporal_variable("power", lower_bound=0, upper_bound=100)
        var.fix(START - TIMESTEP, 50.0)
        var.add_all(TIMES)
        for t in TIMES:
            model.add_constraint(var[t] - var[t - TIMESTEP] <= 10, f"ramp_{t}")
        model.set_direction("maximize")
        model.set_objective(sum(var[t] for t in TIMES))

        assert model.solve().status == SolverStatus.OPTIMAL
        assert [var.solution_value(t) for t in TIMES] == pytest.approx([60.0, 70.0, 80.0])


class TestSolution:
    @pytest.fixture
    def solved(self, model) -> TemporalVariable:
        var = model.add_temporal_variable("power", lower_bound=0, upper_bound=lambda t: 10.0 * t.hour)
        var.fix(START - TIMESTEP, 5.0)
        var.add_all(TIMES)
        model.set_direction("maximize")
        model.set_objective(sum(var[t] for t in TIMES))
        model.solve()
        return var

    def test_solution_value_before_solve_raises(self, model):
        var = model.add_temporal_variable("power")
        var.add(START)

        with pytest.raises(RuntimeError, match="not been solved"):
            var.solution_value(START)

    def test_solution_value_of_fixed_does_not_need_solve(self, model):
        var = model.add_temporal_variable("power")
        var.fix(START, 3.0)

        assert var.solution_value(START) == 3.0

    def test_solution_before_solve_raises(self, model):
        var = model.add_temporal_variable("power", times=TIMES)

        with pytest.raises(RuntimeError, match="not been solved"):
            var.solution()

    def test_solution_returns_model_times(self, solved):
        solution = solved.solution()

        assert isinstance(solution, Timeseries)
        assert [pendulum.instance(t) for t in solution.index] == TIMES
        assert solution.values == pytest.approx([0.0, 10.0, 20.0])

    def test_solution_can_include_fixed(self, solved):
        solution = solved.solution(include_fixed=True)

        assert [pendulum.instance(t) for t in solution.index] == [START - TIMESTEP, *TIMES]
        assert solution.values == pytest.approx([5.0, 0.0, 10.0, 20.0])

    def test_solution_without_variables_raises(self, model):
        var = model.add_temporal_variable("power")
        model.set_direction("minimize")
        model.solve()

        with pytest.raises(ValueError, match="no value to return"):
            var.solution()

    def test_solution_is_picklable(self, solved):
        solution = solved.solution()

        assert pickle.loads(pickle.dumps(solution)) == solution


class TestPickling:
    def test_pickling_is_forbidden(self, model):
        var = model.add_temporal_variable("power", times=TIMES)

        with pytest.raises(TypeError, match="cannot be pickled, use solution"):
            pickle.dumps(var)


def test_repr(model):
    var = model.add_temporal_variable("on", variable_type=VariableType.BOOLEAN, times=TIMES)
    var.fix(START - TIMESTEP, 0)

    assert repr(var) == "TemporalVariable(name=on, type=boolean, variables=3, fixed=1)"
