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
from atlas.solver.temporal_variable import TemporalVariable, TemporalVariableRegistry

START = pendulum.datetime(2025, 1, 1)
TIMESTEP = pendulum.duration(hours=1)
TIMES = [START + k * TIMESTEP for k in range(3)]


@pytest.fixture
def model() -> OptimisationModel:
    return OptimisationModel("SCIP", "test_model")


class TestTimeLabel:
    def test_repeated_hour_at_end_of_daylight_saving_time_keeps_its_offset(self):
        registry = TemporalVariableRegistry()
        summer = pendulum.datetime(2026, 10, 25, 2, tz="Europe/Paris", fold=0)
        winter = pendulum.datetime(2026, 10, 25, 2, tz="Europe/Paris", fold=1)

        assert summer == winter
        assert registry.time_label(summer) == "2026-10-25 02:00:00+02:00"
        assert registry.time_label(winter) == "2026-10-25 02:00:00+01:00"


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

        with pytest.raises(ValueError, match="'power' got duplicate timestamps"):
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

    def test_solution_matches_a_timeseries_built_from_scratch(self, solved):
        expected = Timeseries({"time": TIMES, "value": [solved.solution_value(t) for t in TIMES]})

        assert solved.solution() == expected

    def test_solution_restricted_to_times_in_any_order(self, solved):
        solution = solved.solution([TIMES[2], TIMES[1]])

        assert [pendulum.instance(t) for t in solution.index] == TIMES[1:]
        assert solution.values == pytest.approx([10.0, 20.0])

    def test_solution_restricted_to_times_reads_fixed_values_like_solution_value(self, solved):
        solution = solved.solution([START - TIMESTEP, START])

        assert solution.values == pytest.approx([5.0, 0.0])

    def test_solution_restricted_to_times_rejects_include_fixed(self, solved):
        with pytest.raises(ValueError, match="include_fixed only applies without times"):
            solved.solution([START], include_fixed=True)

    def test_solution_restricted_to_an_unknown_time_raises(self, solved):
        with pytest.raises(KeyError, match="'power' is not defined at"):
            solved.solution([START + 10 * TIMESTEP])

    def test_solution_restricted_to_duplicate_times_raises(self, solved):
        with pytest.raises(ValueError, match="duplicate timestamps"):
            solved.solution([START, START])

    def test_solution_follows_timestamps_added_after_a_first_read(self, model, solved):
        solved.solution()
        later = START + 3 * TIMESTEP
        solved.add(later)
        model.solve()

        assert [pendulum.instance(t) for t in solved.solution().index] == [*TIMES, later]
        assert solved.times == [START - TIMESTEP, *TIMES, later]

    def test_times_returns_a_copy(self, solved):
        solved.model_times.clear()
        solved.times.clear()

        assert solved.model_times == TIMES
        assert len(solved.times) == 4

    def test_solution_values_default_to_sorted_model_times(self, solved):
        assert solved.solution_values() == pytest.approx([0.0, 10.0, 20.0])

    def test_solution_values_follow_the_order_of_times(self, solved):
        assert solved.solution_values([TIMES[2], TIMES[0]]) == pytest.approx([20.0, 0.0])

    def test_solution_values_can_include_fixed(self, solved):
        assert solved.solution_values(include_fixed=True) == pytest.approx([5.0, 0.0, 10.0, 20.0])

    def test_solution_values_of_explicit_times_read_fixed_values(self, solved):
        assert solved.solution_values([START - TIMESTEP, START]) == pytest.approx([5.0, 0.0])

    def test_solution_values_of_explicit_times_reject_include_fixed(self, solved):
        with pytest.raises(ValueError, match="include_fixed only applies without times"):
            solved.solution_values([START], include_fixed=True)

    def test_solution_values_of_an_unknown_time_raise(self, solved):
        with pytest.raises(KeyError, match="'power' is not defined at"):
            solved.solution_values([START + 10 * TIMESTEP])

    def test_solution_values_before_solve_raises(self, model):
        var = model.add_temporal_variable("power", times=TIMES)

        with pytest.raises(RuntimeError, match="not been solved"):
            var.solution_values()


class TestPickling:
    def test_pickling_is_forbidden(self, model):
        var = model.add_temporal_variable("power", times=TIMES)

        with pytest.raises(TypeError, match="cannot be pickled, use solution"):
            pickle.dumps(var)


def test_repr(model):
    var = model.add_temporal_variable("on", variable_type=VariableType.BOOLEAN, times=TIMES)
    var.fix(START - TIMESTEP, 0)

    assert repr(var) == "TemporalVariable(name=on, type=boolean, variables=3, fixed=1)"


def _coefficients(model, name, variables):
    constraint = model.get_constraint(name)
    return [constraint.GetCoefficient(v) for v in variables], (constraint.lb(), constraint.ub())


class TestSum:
    def test_sums_model_times_by_default(self, model):
        var = model.add_temporal_variable("power", TIMES)
        var.fix(START - TIMESTEP, 5.0)

        model.add_constraint(var.sum() <= 10, "total")

        assert _coefficients(model, "total", [var[t] for t in TIMES]) == ([1.0] * 3, (float("-inf"), 10.0))

    def test_explicit_times_include_fixed_values(self, model):
        var = model.add_temporal_variable("power", TIMES)
        var.fix(START - TIMESTEP, 5.0)

        model.add_constraint(var.sum([START - TIMESTEP, TIMES[0]]) <= 10, "total")

        assert _coefficients(model, "total", [var[TIMES[0]], var[TIMES[1]]]) == ([1.0, 0.0], (float("-inf"), 5.0))

    @pytest.mark.parametrize(
        "weights",
        [
            pytest.param(Timeseries({"time": TIMES, "value": [1.0, 2.0, 3.0]}), id="timeseries"),
            pytest.param(lambda t: float(t.hour + 1), id="callable"),
        ],
    )
    def test_time_dependent_weights(self, model, weights):
        var = model.add_temporal_variable("power", TIMES)

        model.add_constraint(var.sum(weights=weights) <= 10, "total")

        assert _coefficients(model, "total", [var[t] for t in TIMES])[0] == [1.0, 2.0, 3.0]

    def test_constant_weight(self, model):
        var = model.add_temporal_variable("power", TIMES)

        model.add_constraint(var.sum(weights=0.5) <= 10, "total")

        assert _coefficients(model, "total", [var[t] for t in TIMES])[0] == [0.5] * 3

    def test_unknown_time_raises(self, model):
        var = model.add_temporal_variable("power", TIMES)

        with pytest.raises(KeyError, match="is not defined at"):
            var.sum([START - TIMESTEP])


class TestFixAll:
    def test_fixes_a_sequence(self, model):
        var = model.add_temporal_variable("power")

        var.fix_all(TIMES, [1.0, 2.0, 3.0])

        assert [var[t] for t in TIMES] == [1.0, 2.0, 3.0]
        assert model.variables == set()

    def test_reads_a_timeseries_in_one_lookup(self, model):
        values = Timeseries({"time": TIMES, "value": [1.0, 2.0, 3.0]})
        var = model.add_temporal_variable("power")

        with patch.object(Timeseries, "get_values", autospec=True, side_effect=Timeseries.get_values) as get_values:
            var.fix_all(TIMES, values)

        assert get_values.call_count == 1
        assert var.times == TIMES

    def test_length_mismatch_raises_before_fixing(self, model):
        var = model.add_temporal_variable("power")

        with pytest.raises(ValueError, match="got 2 values for 3 timestamps"):
            var.fix_all(TIMES, [1.0, 2.0])

        assert len(var) == 0

    def test_clash_raises_before_fixing(self, model):
        var = model.add_temporal_variable("power", [TIMES[2]])

        with pytest.raises(ValueError, match="already holds a solver variable"):
            var.fix_all(TIMES, [1.0, 2.0, 3.0])

        assert var.times == [TIMES[2]]

    def test_duplicates_raise_before_fixing(self, model):
        var = model.add_temporal_variable("power")

        with pytest.raises(ValueError, match="'power' got duplicate timestamps"):
            var.fix_all([TIMES[0], TIMES[0]], [1.0, 2.0])

        assert len(var) == 0


class TestSetBounds:
    def test_single_timestamp(self, model):
        var = model.add_temporal_variable("power", TIMES)

        var.set_bounds(TIMES[1], 1.0, 2.0)

        assert (var[TIMES[1]].lb(), var[TIMES[1]].ub()) == (1.0, 2.0)
        assert var[TIMES[0]].ub() == float("inf")

    def test_defaults_to_model_times_and_keeps_omitted_bound(self, model):
        var = model.add_temporal_variable("power", TIMES, lower_bound=-5.0, upper_bound=5.0)

        var.set_bounds(upper_bound=Timeseries({"time": TIMES, "value": [1.0, 2.0, 3.0]}))

        assert [(var[t].lb(), var[t].ub()) for t in TIMES] == [(-5.0, 1.0), (-5.0, 2.0), (-5.0, 3.0)]

    def test_declaration_bounds_still_apply_to_later_variables(self, model):
        var = model.add_temporal_variable("power", TIMES, upper_bound=5.0)

        var.set_bounds(upper_bound=1.0)

        assert var.add(TIMES[-1] + TIMESTEP).ub() == 5.0

    def test_defaults_skip_fixed_timestamps(self, model):
        var = model.add_temporal_variable("power", TIMES)
        var.fix(START - TIMESTEP, 0.0)

        var.set_bounds(upper_bound=1.0)

        assert [var[t].ub() for t in TIMES] == [1.0, 1.0, 1.0]

    def test_fixed_timestamp_raises_before_changing_bounds(self, model):
        var = model.add_temporal_variable("power", TIMES)
        var.fix(START - TIMESTEP, 0.0)

        with pytest.raises(ValueError, match="holds a fixed value"):
            var.set_bounds([TIMES[0], START - TIMESTEP], 1.0, 2.0)

        assert var[TIMES[0]].lb() == float("-inf")

    def test_unknown_timestamp_raises_before_changing_bounds(self, model):
        var = model.add_temporal_variable("power", TIMES)

        with pytest.raises(KeyError, match="is not defined at"):
            var.set_bounds([TIMES[0], START - TIMESTEP], 1.0, 2.0)

        assert var[TIMES[0]].lb() == float("-inf")
