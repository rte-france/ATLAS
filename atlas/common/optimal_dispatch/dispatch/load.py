"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pendulum import DateTime

    from atlas.abstract_class.parameters import AbstractModuleParameters
    from atlas.common.optimal_dispatch.input_objects.load import LoadDispatchInput
    from atlas.solver.temporal_variable import TemporalVariable


class LoadDispatch:
    """
    Physical dispatch component for a single load unit.

    Load is consumption-only — its ``{name}_power_level`` temporal variable is bounded
    by ``[max_power, 0]`` where ``max_power`` is the *negative-valued* forecasted demand.
    Adds two physical constraints per timestep (``power ≥ max_power`` and ``power ≤ 0``),
    redundant with the variable bounds but emitted for LP-parity.

    No reserves are handled — loads do not participate in reserve markets in this model.

    Typical usage::

        dispatch = LoadDispatch(equipment)
        dispatch.setup(model, parameters)
        dispatch.add_variables(time_window)
        for time in time_window:
            dispatch.add_constraints(model, time)
    """

    def __init__(self, equipment: LoadDispatchInput) -> None:
        self._eq = equipment
        self._execution_date: DateTime = None  # type: ignore[assignment]
        self.power_level: TemporalVariable = None  # type: ignore[assignment]

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters) -> None:
        """Bind to a solver model and declare the power-level temporal variable."""
        self._execution_date = parameters.temporal.execution_date
        self.power_level = model.add_temporal_variable(
            f"{self._eq.name}_power_level", lower_bound=self.max_power, upper_bound=0
        )

    def add_variables(self, times: Iterable[DateTime]) -> None:
        """Register the power-level variables for *times* in the model."""
        self.power_level.add_all(times)

    def add_constraints(self, model: OptimisationModel, time: DateTime) -> None:
        """Add ``power ≥ max_power`` and ``power ≤ 0`` at *time*."""
        n = self._eq.name
        max_p = self.max_power(time)
        power_level_var = self.power_level[time]
        model.add_constraint(power_level_var >= max_p, f"power_max_{time}_{n}")
        model.add_constraint(power_level_var <= 0, f"power_min_{time}_{n}")

    def max_power(self, time: DateTime) -> float:
        """Forecast-driven *lower* bound on power (negative for consumption), or 0 when unavailable."""
        fm = self._eq.maximum_power_forecast
        if fm is None or not fm.indexes:
            return 0.0
        return fm.get_forecast(self._execution_date, time, time, default_value=0).get_value(time)
