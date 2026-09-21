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


class TestApplyOnParametersForced:
    def test_forced_overrides_explicit_value(self):
        parameters = _make_parameters(label="from-task")
        context = ContextParameters(forced={"label": "from-context"})

        result = context.apply_on_parameters(parameters)

        assert result.label == "from-context"

    def test_forced_overrides_regardless_of_inplace_flag(self):
        parameters = _make_parameters(label="from-task")
        context = ContextParameters(forced={"label": "from-context"})

        result = context.apply_on_parameters(parameters, inplace=True)

        assert result.label == "from-context"


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


class TestApplyOnParametersPrecedence:
    def test_forced_wins_over_default_on_same_field(self):
        parameters = _make_parameters(label="from-task")
        context = ContextParameters(
            default={"label": "from-default"},
            forced={"label": "from-forced"},
        )

        result = context.apply_on_parameters(parameters)

        assert result.label == "from-forced"


class TestApplyOnParametersRobustness:
    def test_unknown_fields_are_ignored(self):
        """default/forced keys that don't exist on the parameters object must be dropped
        silently, not raise and not get attached to the result."""
        parameters = _make_parameters()
        context = ContextParameters(
            default={"does_not_exist": "x"},
            forced={"also_missing": "y"},
        )

        result = context.apply_on_parameters(parameters)

        assert not hasattr(result, "does_not_exist")
        assert not hasattr(result, "also_missing")

    def test_multiple_fields_do_not_raise(self):
        """Regression test for the 'too many values to unpack' bug: applying more than
        one default/forced field at once used to crash outright."""
        parameters = _make_parameters()
        context = ContextParameters(
            default={"solver_name": "HiGHS"},
            forced={"label": "forced-label"},
        )

        result = context.apply_on_parameters(parameters)

        assert result.solver_name == "HiGHS"
        assert result.label == "forced-label"

    def test_single_field_with_long_key_does_not_raise(self):
        """Even a single field used to crash unless its name happened to be exactly two
        characters (since the buggy code unpacked each dict key as if it were a
        two-item (k, v) pair)."""
        parameters = _make_parameters()
        context = ContextParameters(forced={"solver_name": "HiGHS"})

        result = context.apply_on_parameters(parameters)

        assert result.solver_name == "HiGHS"

    def test_empty_context_returns_unchanged_copy(self):
        parameters = _make_parameters(label="from-task", solver_name="XPRESS")
        context = ContextParameters()

        result = context.apply_on_parameters(parameters)

        assert result is not parameters
        assert result.label == parameters.label
        assert result.solver_name == parameters.solver_name


class TestApplyOnParametersReturnValue:
    def test_return_type_preserves_concrete_subclass(self):
        """Regression test for the mypy error: apply_on_parameters used to be typed to
        return the base `Parameters` class, so a caller assigning the result back to a
        variable typed as the concrete subclass got an 'Incompatible types in
        assignment' error, even though the runtime object was always the right type."""
        parameters = _make_parameters()
        context = ContextParameters(forced={"label": "x"})

        result = context.apply_on_parameters(parameters)

        assert isinstance(result, _DummyModuleParameters)

    def test_does_not_mutate_original(self):
        """`apply_on_parameters` always returns a new object via `model_copy`, whatever
        the `inplace` flag is set to — it never mutates the parameters object it's given."""
        parameters = _make_parameters(label="from-task")
        context = ContextParameters(forced={"label": "from-context"})

        context.apply_on_parameters(parameters, inplace=True)

        assert parameters.label == "from-task"


class TestApplyOnParametersDeepFlag:
    """`inplace` is actually forwarded as pydantic's `model_copy(deep=...)`, not a true
    in-place mutation flag (see TestApplyOnParametersReturnValue.test_does_not_mutate_original)
    — it only controls whether fields untouched by default/forced are deep- or
    shallow-copied. These tests pin that current behaviour down."""

    def test_inplace_true_deep_copies_untouched_nested_field(self):
        parameters = _make_parameters()
        context = ContextParameters(forced={"label": "x"})

        result = context.apply_on_parameters(parameters, inplace=True)
        result.output.output_dir = "mutated"

        assert parameters.output.output_dir != "mutated"

    def test_inplace_false_shares_untouched_nested_field(self):
        parameters = _make_parameters()
        context = ContextParameters(forced={"label": "x"})

        result = context.apply_on_parameters(parameters, inplace=False)

        assert result.output is parameters.output