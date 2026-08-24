"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.solver.model_var import ModelVar
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.abstract_class.parameters import AbstractModuleParameters
    from atlas.common.optimal_dispatch.input_objects.load import LoadDispatchInput


class LoadDispatch:
    """
    Physical dispatch component for a single load unit.

    Load is consumption-only — its ``{name}_power_level_{time}`` variable is bounded
    by ``[max_power, 0]`` where ``max_power`` is the *negative-valued* forecasted demand.
    Adds two physical constraints per timestep (``power ≥ max_power`` and ``power ≤ 0``),
    redundant with the variable bounds but emitted for LP-parity.

    No reserves are handled — loads do not participate in reserve markets in this model.

    Typical usage::

        dispatch = LoadDispatch(equipment)
        dispatch.setup(model, parameters)
        for time in time_window:
            dispatch.add_variables(time)
        for time in time_window:
            dispatch.add_constraints(model, time)
    """

    def __init__(self, equipment: LoadDispatchInput) -> None:
        self._eq = equipment
        self._model: OptimisationModel = None  # type: ignore[assignment]
        self._execution_date: DateTime = None  # type: ignore[assignment]
        self.power_level_var: ModelVar = None  # type: ignore[assignment]

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters) -> None:
        """Bind to a solver model and prepare the variable handle."""
        self._execution_date = parameters.temporal.execution_date
        self._model = model
        n = self._eq.name
        self.power_level_var = ModelVar(
            getter=lambda time: model.get_variable(f"{n}_power_level_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{n}_power_level_{time}", lower_bound=self.max_power(time), upper_bound=0
            ),
        )

    def add_variables(self, time: DateTime) -> None:
        """Register the power-level variable for *time* in the model."""
        self.power_level_var.set_model_var(time)

    def add_constraints(self, model: OptimisationModel, time: DateTime) -> None:
        """Add ``power ≥ max_power`` and ``power ≤ 0`` at *time*."""
        n = self._eq.name
        max_p = self.max_power(time)
        power_level_var = self.power_level_var.get_value(time)
        model.add_constraint(power_level_var >= max_p, f"power_max_{time}_{n}")
        model.add_constraint(power_level_var <= 0, f"power_min_{time}_{n}")

    def max_power(self, time: DateTime) -> float:
        """Forecast-driven *lower* bound on power (negative for consumption), or 0 when unavailable.

        Uses the pre-fetched ``_cached_forecast`` when present; falls back to querying
        ``maximum_power_forecast`` directly so the dispatch remains valid even when
        ``prefetch_forecasts`` has not been called.
        """
        forecast = getattr(self._eq, "_cached_forecast", None)
        if forecast is not None and time in forecast:
            return forecast.get_value(time)
        fm = self._eq.maximum_power_forecast
        if fm is not None and self._execution_date in fm:
            fallback = fm.get_forecast(self._execution_date, time, time)
            if time in fallback:
                return fallback.get_value(time)
        return 0.0
