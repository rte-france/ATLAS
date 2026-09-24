"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Family of optimisation variables indexed by time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, NoReturn

from pendulum import DateTime

from atlas.enums import VariableType
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.timeseries import Timeseries

if TYPE_CHECKING:
    # ortools-stubs does not ship pywraplp (see the solver_interface mypy override)
    from ortools.linear_solver import pywraplp  # type: ignore[attr-defined]

    from atlas.solver.solver_interface import OptimisationModel

type Bound = float | AbstractTimeseries | Callable[[DateTime], float]

# Same defaults as OptimisationModel.add_continuous_variable / add_integer_variable
_DEFAULT_BOUNDS: dict[VariableType, tuple[float, float]] = {
    VariableType.CONTINUOUS: (float("-inf"), float("inf")),
    VariableType.INTEGER: (0.0, float("inf")),
}


class TemporalVariable:
    """
    Family of optimisation variables sharing a name and indexed by :class:`~pendulum.DateTime`.

    Each timestamp holds either a solver variable, created with :meth:`add`, or a fixed value,
    set with :meth:`fix` (e.g. initial conditions outside the optimisation horizon).
    Indexing returns either one transparently, so constraints can reference past timestamps
    without distinguishing the two.

    Solver variables are named ``{name}_{t}``. The object holds references to the solver and
    therefore cannot be pickled: use :meth:`solution` to get a picklable result.

    Do not instantiate directly: use :meth:`~atlas.solver.solver_interface.OptimisationModel.add_temporal_variable`,
    which registers the family in the model.

    **Example**

        power = model.add_temporal_variable("unit_power", time_window, lower_bound=0, upper_bound=max_power)
        power.fix(start - timestep, 50.0)          # initial condition
        power.add(end)                             # one more solver variable
        for t in time_window:
            model.add_constraint(power[t] - power[t - timestep] <= ramp, f"ramp_{t}")
        model.solve()
        power.solution()                           # Timeseries over the solver variables

    :param model: Optimisation model in which variables are created
    :type model: OptimisationModel
    :param name: Name of the family, used as prefix of each solver variable name
    :type name: str
    :param times: Timestamps for which solver variables are created immediately
    :type times: Iterable[DateTime] | None
    :param variable_type: Type of the solver variables, defaults to continuous
    :type variable_type: VariableType
    :param lower_bound: Lower bound: a constant, a timeseries or a function of time. Defaults to the
        model default for the variable type. Not allowed for boolean variables. A timeseries is read
        for all timestamps at once when variables are created in bulk, which is much faster.
    :type lower_bound: float | AbstractTimeseries | Callable[[DateTime], float] | None
    :param upper_bound: Upper bound, same forms and default as *lower_bound*
    :type upper_bound: float | AbstractTimeseries | Callable[[DateTime], float] | None
    :raises ValueError: If bounds are given for a boolean variable
    """

    def __init__(
        self,
        model: OptimisationModel,
        name: str,
        times: Iterable[DateTime] | None = None,
        variable_type: VariableType = VariableType.CONTINUOUS,
        lower_bound: Bound | None = None,
        upper_bound: Bound | None = None,
    ) -> None:
        if variable_type == VariableType.BOOLEAN and (lower_bound is not None or upper_bound is not None):
            raise ValueError(f"Boolean temporal variable '{name}' does not accept bounds")

        self._model = model
        self._name = name
        self._variable_type = variable_type
        default_lower, default_upper = _DEFAULT_BOUNDS.get(variable_type, (0.0, 1.0))
        self._lower_bound: Bound = default_lower if lower_bound is None else lower_bound
        self._upper_bound: Bound = default_upper if upper_bound is None else upper_bound
        self._variables: dict[DateTime, pywraplp.Variable] = {}
        self._fixed: dict[DateTime, float] = {}

        if times is not None:
            self.add_all(times)

    @property
    def name(self) -> str:
        """Return the name of the family."""
        return self._name

    @property
    def variable_type(self) -> VariableType:
        """Return the type of the solver variables."""
        return self._variable_type

    @property
    def times(self) -> list[DateTime]:
        """Return the sorted timestamps holding either a solver variable or a fixed value."""
        return sorted(self._variables.keys() | self._fixed.keys())

    @property
    def model_times(self) -> list[DateTime]:
        """Return the sorted timestamps holding a solver variable."""
        return sorted(self._variables)

    def add(self, t: DateTime) -> pywraplp.Variable:
        """
        Create the solver variable at *t*, evaluating time-dependent bounds at *t*.

        Prefer :meth:`add_all` (or the ``times`` argument at declaration) for several timestamps:
        it reads timeseries bounds in one lookup.

        :param t: Timestamp of the variable
        :type t: DateTime
        :return: The created solver variable
        :rtype: pywraplp.Variable
        :raises ValueError: If *t* already holds a solver variable or a fixed value
        :raises KeyError: If a timeseries bound has no value at *t*
        """
        self._check_undefined(t)
        name = f"{self._name}_{t}"
        if self._variable_type == VariableType.BOOLEAN:
            variable = self._model.add_boolean_variable(name)
        else:
            lower, upper = _resolve(self._lower_bound, t), _resolve(self._upper_bound, t)
            variable = self._create_bounded()(name, lower, upper)
        self._variables[t] = variable
        return variable

    def add_all(self, times: Iterable[DateTime]) -> None:
        """
        Create one solver variable per timestamp in *times*.

        All timestamps are checked before any variable is created, and timeseries bounds are
        read for all timestamps in one lookup.

        :param times: Timestamps of the variables
        :type times: Iterable[DateTime]
        :raises ValueError: If *times* contains duplicates, or if a timestamp already holds a solver
            variable or a fixed value
        :raises KeyError: If a timeseries bound has no value at one of the timestamps
        """
        times = list(times)
        self._check_all_undefined(times)

        if self._variable_type == VariableType.BOOLEAN:
            for t in times:
                self._variables[t] = self._model.add_boolean_variable(f"{self._name}_{t}")
            return

        lowers = _resolve_all(self._lower_bound, times)
        uppers = _resolve_all(self._upper_bound, times)
        create = self._create_bounded()
        for t, lower, upper in zip(times, lowers, uppers, strict=True):
            self._variables[t] = create(f"{self._name}_{t}", lower, upper)

    def fix(self, t: DateTime, value: float) -> None:
        """
        Set a fixed value at *t*, typically an initial condition outside the optimisation horizon.

        :param t: Timestamp of the value
        :type t: DateTime
        :param value: The fixed value
        :type value: float
        :raises ValueError: If *t* already holds a solver variable or a fixed value
        """
        self._check_undefined(t)
        self._fixed[t] = value

    def is_fixed(self, t: DateTime) -> bool:
        """
        Tell whether *t* holds a fixed value.

        :param t: Timestamp to check
        :type t: DateTime
        :return: True if *t* holds a fixed value, False otherwise
        :rtype: bool
        """
        return t in self._fixed

    def solution_value(self, t: DateTime) -> float:
        """
        Get the solved value at *t*, or the fixed value if *t* holds one.

        :param t: Timestamp of the value
        :type t: DateTime
        :return: The value at *t*
        :rtype: float
        :raises RuntimeError: If *t* holds a solver variable and the model has not been solved
        :raises KeyError: If *t* was never added
        """
        if t in self._fixed:
            return self._fixed[t]
        variable = self._get_variable(t)
        self._check_solved()
        return variable.solution_value()

    def solution(self, include_fixed: bool = False) -> Timeseries:
        """
        Get the solved values as a picklable :class:`~atlas.math.timeseries.Timeseries`.

        :param include_fixed: Also include fixed values, defaults to False
        :type include_fixed: bool
        :return: Values indexed by timestamp
        :rtype: Timeseries
        :raises RuntimeError: If the model has not been solved
        :raises ValueError: If there is no value to return
        """
        self._check_solved()
        times = self.times if include_fixed else self.model_times
        if not times:
            raise ValueError(f"Temporal variable '{self._name}' has no value to return")
        return Timeseries(
            {"time": times, "value": [self.solution_value(t) for t in times]},
            timezone=times[0].timezone_name or "UTC",
        )

    def __getitem__(self, t: DateTime) -> pywraplp.Variable | float:
        """
        Get the solver variable or the fixed value at *t*.

        :param t: Timestamp
        :type t: DateTime
        :return: The fixed value if *t* holds one, the solver variable otherwise
        :rtype: pywraplp.Variable | float
        :raises KeyError: If *t* was never added
        """
        if t in self._fixed:
            return self._fixed[t]
        return self._get_variable(t)

    def __contains__(self, t: object) -> bool:
        """Tell whether *t* holds a solver variable or a fixed value."""
        return t in self._variables or t in self._fixed

    def __len__(self) -> int:
        """Return the number of timestamps holding a solver variable or a fixed value."""
        return len(self._variables) + len(self._fixed)

    def __getstate__(self) -> NoReturn:
        """
        Forbid pickling: solver variables cannot cross a process boundary.

        :raises TypeError: Always
        """
        raise TypeError(
            f"TemporalVariable '{self._name}' holds solver objects and cannot be pickled, "
            "use solution() to get a picklable result"
        )

    def __repr__(self) -> str:
        """String representation of the temporal variable."""
        return (
            f"TemporalVariable(name={self._name}, type={self._variable_type.value}, "
            f"variables={len(self._variables)}, fixed={len(self._fixed)})"
        )

    def _create_bounded(self) -> Callable[[str, float, float], pywraplp.Variable]:
        if self._variable_type == VariableType.INTEGER:
            return self._model.add_integer_variable
        return self._model.add_continuous_variable

    def _get_variable(self, t: DateTime) -> pywraplp.Variable:
        try:
            return self._variables[t]
        except KeyError:
            raise KeyError(f"Temporal variable '{self._name}' is not defined at {t}") from None

    def _check_undefined(self, t: DateTime) -> None:
        if t in self._variables:
            raise ValueError(f"Temporal variable '{self._name}' already holds a solver variable at {t}")
        if t in self._fixed:
            raise ValueError(f"Temporal variable '{self._name}' already holds a fixed value at {t}")

    def _check_all_undefined(self, times: list[DateTime]) -> None:
        unique = set(times)
        if len(unique) != len(times):
            raise ValueError(f"Temporal variable '{self._name}' cannot add duplicate timestamps at once")
        if clash := unique & self._variables.keys():
            raise ValueError(f"Temporal variable '{self._name}' already holds a solver variable at {min(clash)}")
        if clash := unique & self._fixed.keys():
            raise ValueError(f"Temporal variable '{self._name}' already holds a fixed value at {min(clash)}")

    def _check_solved(self) -> None:
        if self._model.solution_info is None:
            raise RuntimeError(f"Optimisation model has not been solved yet, cannot read '{self._name}'")


def _resolve(bound: Bound, t: DateTime) -> float:
    if isinstance(bound, AbstractTimeseries):
        return bound.get_value(t)
    if callable(bound):
        return bound(t)
    return bound


def _resolve_all(bound: Bound, times: Sequence[DateTime]) -> Sequence[float]:
    if isinstance(bound, AbstractTimeseries):
        return bound.get_values(times)
    if callable(bound):
        return [bound(t) for t in times]
    return [bound] * len(times)
