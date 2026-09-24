from __future__ import annotations

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.io_utils.parameters import ContextParameters, DateParameters


class _DummyModuleParameters(AbstractModuleParameters):
    """Minimal concrete AbstractModuleParameters subclass, used only to exercise
    ContextParameters.apply_on_parameters against a realistic parameters object."""

    solver_name: str | None = None
    label: str = "unset"


def _make_parameters(**overrides) -> _DummyModuleParameters:
    base = {
        "temporal": DateParameters(
            start_date="2024-01-01T00:00:00",
            end_date="2024-01-02T00:00:00",
            execution_date="2024-01-01T00:00:00",
        ),
    }
    base.update(overrides)
    return _DummyModuleParameters(**base)


class TestApplyOnParametersDefault:
    def test_default_fills_none_field(self):
        parameters = _make_parameters(solver_name=None)
        context = ContextParameters(default={"solver_name": "HiGHS"})

        result = context.apply_on_parameters(parameters)

        assert result.solver_name == "HiGHS"

    def test_default_does_not_override_existing_value(self):
        parameters = _make_parameters(solver_name="XPRESS")
        context = ContextParameters(default={"solver_name": "HiGHS"})

        result = context.apply_on_parameters(parameters)

        assert result.solver_name == "XPRESS"


class TestApplyOnParametersForced:
    def test_forced_overrides_explicit_value(self):
        parameters = _make_parameters(label="from-task")
        context = ContextParameters(forced={"label": "from-context"})

        result = context.apply_on_parameters(parameters)

        assert result.label == "from-context"


class TestApplyOnParametersRobustness:
    def test_forced_wins_over_default_on_same_field(self):
        parameters = _make_parameters(label="from-task")
        context = ContextParameters(
            default={"label": "from-default"},
            forced={"label": "from-forced"},
        )

        result = context.apply_on_parameters(parameters)

        assert result.label == "from-forced"

    def test_unknown_fields_are_ignored(self):
        parameters = _make_parameters()
        context = ContextParameters(
            default={"does_not_exist": "x"},
            forced={"also_missing": "y"},
        )

        result = context.apply_on_parameters(parameters)

        assert not hasattr(result, "does_not_exist")
        assert not hasattr(result, "also_missing")

    def test_multiple_fields(self):
        parameters = _make_parameters()
        context = ContextParameters(
            default={"solver_name": "HiGHS"},
            forced={"label": "forced-label"},
        )

        result = context.apply_on_parameters(parameters)

        assert result.solver_name == "HiGHS"
        assert result.label == "forced-label"

    def test_empty_context_returns_unchanged_copy(self):
        parameters = _make_parameters(label="from-task", solver_name="XPRESS")
        context = ContextParameters()

        result = context.apply_on_parameters(parameters)

        assert result is not parameters
        assert result.label == parameters.label
        assert result.solver_name == parameters.solver_name

    def test_return_type_preserves_concrete_subclass(self):
        parameters = _make_parameters()
        context = ContextParameters(forced={"label": "x"})

        result = context.apply_on_parameters(parameters)

        assert isinstance(result, _DummyModuleParameters)

    def test_untouched_given_parameters(self):
        parameters = _make_parameters(label="from-task", solver_name="XPRESS")
        context = ContextParameters(
            default={"solver_name": "HiGHS"},
            forced={"label": "forced-label"},
        )

        result = context.apply_on_parameters(parameters)

        assert result is not parameters
        assert parameters.label == "from-task"
        assert parameters.solver_name == "XPRESS"
