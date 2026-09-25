"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pickle

import pendulum
import pytest

from atlas.enums import VariableType
from atlas.solver.solver_interface import OptimisationModel
from atlas.solver.temporal_variable import TemporalVariable

START = pendulum.datetime(2025, 1, 1)
TIMESTEP = pendulum.duration(hours=1)
TIMES = [START + k * TIMESTEP for k in range(3)]


@pytest.fixture
def model() -> OptimisationModel:
    return OptimisationModel("SCIP", "test_model")


class TestAddTemporalVariable:
    def test_creates_variables_over_times(self, model):
        power = model.add_temporal_variable("power", TIMES, lower_bound=0, upper_bound=10)

        assert isinstance(power, TemporalVariable)
        assert power.model_times == TIMES
        assert model.variables == {f"power_{t}" for t in TIMES}
        assert (power[START].lb(), power[START].ub()) == (0, 10)

    def test_times_is_optional(self, model):
        power = model.add_temporal_variable("power")

        assert len(power) == 0
        assert model.variables == set()

    def test_forwards_variable_type(self, model):
        on = model.add_temporal_variable("on", TIMES, VariableType.BOOLEAN)

        assert on.variable_type == VariableType.BOOLEAN
        assert on[START].integer()

    def test_boolean_with_bounds_raises_and_is_not_registered(self, model):
        with pytest.raises(ValueError, match="does not accept bounds"):
            model.add_temporal_variable("on", TIMES, VariableType.BOOLEAN, upper_bound=1)

        model.add_temporal_variable("on", TIMES, VariableType.BOOLEAN)

    def test_duplicate_name_raises(self, model):
        model.add_temporal_variable("power")

        with pytest.raises(ValueError, match="Temporal variable 'power' already exists"):
            model.add_temporal_variable("power", variable_type=VariableType.BOOLEAN)

    def test_clear_resets_registry(self, model):
        model.add_temporal_variable("power", TIMES)

        model.clear()
        model.add_temporal_variable("other", TIMES)
        model.set_direction("minimize")
        model.solve()

        assert set(model.solution()) == {"other"}
        model.add_temporal_variable("power", TIMES)


class TestSolution:
    @pytest.fixture
    def solved(self, model) -> OptimisationModel:
        power = model.add_temporal_variable("power", lower_bound=0, upper_bound=lambda t: 10.0 * t.hour)
        power.fix(START - TIMESTEP, 5.0)
        power.add_all(TIMES)
        on = model.add_temporal_variable("on", TIMES, VariableType.BOOLEAN)
        initial = model.add_temporal_variable("initial")
        initial.fix(START, 1.0)
        for t in TIMES:
            model.add_constraint(power[t] <= 100 * on[t], f"power_on_{t}")
        model.set_direction("maximize")
        model.set_objective(sum(power[t] - on[t] for t in TIMES))
        model.solve()
        return model

    def test_before_solve_raises(self, model):
        model.add_temporal_variable("power", TIMES)

        with pytest.raises(RuntimeError, match="not been solved"):
            model.solution()

    def test_returns_solved_values_by_name(self, solved):
        solution = solved.solution()

        assert set(solution) == {"power", "on"}
        assert solution["power"].values == pytest.approx([0.0, 10.0, 20.0])
        assert solution["on"].values == pytest.approx([0.0, 1.0, 1.0])

    def test_include_fixed(self, solved):
        solution = solved.solution(include_fixed=True)

        assert set(solution) == {"power", "on", "initial"}
        assert solution["power"].values == pytest.approx([5.0, 0.0, 10.0, 20.0])
        assert solution["initial"].values == [1.0]

    def test_empty_when_no_temporal_variable(self, model):
        model.set_direction("minimize")
        model.solve()

        assert model.solution() == {}

    def test_is_picklable(self, solved):
        solution = solved.solution()

        restored = pickle.loads(pickle.dumps(solution))

        assert restored.keys() == solution.keys()
        assert all(restored[name] == solution[name] for name in solution)

    def test_matches_name_based_access(self, solved):
        """Temporal variables stay reachable by name, so migrated and legacy code can coexist."""
        solution = solved.solution()

        for k, t in enumerate(TIMES):
            assert solved.get_variable_value(f"power_{t}") == pytest.approx(solution["power"].values[k])
