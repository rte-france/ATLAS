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
    from atlas.common.optimal_dispatch.input_objects.renewable import RenewableDispatchInput
    from atlas.math.timeseries import Timeseries
    from atlas.solver.temporal_variable import TemporalVariable


class RenewableDispatch:
    """
    Physical dispatch component for a single renewable (wind or solar) unit.

    Owns the ``{name}_power_level`` temporal variable, bounded at each timestep by
    ``[min_power, max_power]`` where:

    - ``max_power = forecast(time)``
    - ``min_power = (1 - curtailment_ratio(time)) × max_power``

    Adds two physical constraints per timestep (``power ≤ max_power`` and ``power ≥ min_power``)
    on top of the variable bounds — the constraints are kept explicit for solver-LP
    output stability with the existing reference files. Does **not** handle reserves
    or objective terms.

    Typical usage::

        dispatch = RenewableDispatch(equipment)
        dispatch.setup(model, parameters)
        dispatch.add_variables(time_window)
        for time in time_window:
            dispatch.add_constraints(model, time)
    """

    def __init__(self, equipment: RenewableDispatchInput) -> None:
        self._eq = equipment
        self._execution_date: DateTime = None  # type: ignore[assignment]
        self._forecast: Timeseries | None = None

        self.power_level: TemporalVariable = None  # type: ignore[assignment]

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters) -> None:
        """
        Bind to a solver model and declare the power-level temporal variable.

        Must be called before :meth:`add_variables` or :meth:`add_constraints`.

        :param model: The optimisation model.
        :param parameters: Module parameters, giving the execution date the forecasts are read at.
        """
        self._execution_date = parameters.temporal.execution_date
        self.power_level = model.add_temporal_variable(
            f"{self._eq.name}_power_level", lower_bound=0, upper_bound=self.max_power
        )

    def add_variables(self, times: Iterable[DateTime]) -> None:
        """
        Register the power-level variables for *times* in the model.

        The maximum-power forecast is read once over *times*, :meth:`max_power` then serves it.
        """
        times = list(times)
        if times:
            self._forecast = self._eq.maximum_power_forecast.get_forecast(
                self._execution_date, min(times), max(times), default_value=0
            )
        self.power_level.add_all(times)

    def add_constraints(self, model: OptimisationModel, time: DateTime) -> None:
        """
        Add ``power_level ≤ max_power`` and ``power_level ≥ min_power`` at *time*.

        These are redundant with the variable bounds (which the solver enforces directly)
        but are emitted explicitly for parity with the prior step formulation and the
        reference LP files.
        """
        n = self._eq.name
        max_p = self.max_power(time)
        min_p = self.min_power(time)

        power_level_var = self.power_level[time]
        model.add_constraint(power_level_var <= max_p, f"power_max_{time}_{n}")
        model.add_constraint(power_level_var >= min_p, f"power_min_{time}_{n}")

    def max_power(self, time: DateTime) -> float:
        """
        Forecast-driven upper bound on power, or 0 when no forecast covers *time*.

        Only defined at the times given to :meth:`add_variables`.
        """
        return self._forecast.get_value(time) if self._forecast is not None else 0.0

    def min_power(self, time: DateTime) -> float:
        """Curtailment-driven lower bound: ``(1 - curtailment_ratio) × max_power``."""
        return (1 - self._eq.maximum_curtailment_ratio.get_value(time)) * self.max_power(time)
