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
    from atlas.common.optimal_dispatch.input_objects.renewable import RenewableDispatchInput


class RenewableDispatch:
    """
    Physical dispatch component for a single renewable (wind or solar) unit.

    Owns one ``{name}_power_level_{time}`` variable per timestep, bounded by
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
        for time in time_window:
            dispatch.add_variables(time)
        for time in time_window:
            dispatch.add_constraints(model, time)
    """

    def __init__(self, equipment: RenewableDispatchInput) -> None:
        self._eq = equipment
        self._model: OptimisationModel = None  # type: ignore[assignment]

        self.power_level_var: ModelVar = None  # type: ignore[assignment]

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters) -> None:
        """
        Bind to a solver model and prepare the variable handle.

        Must be called before :meth:`add_variables` or :meth:`add_constraints`.
        The equipment's ``_cached_forecast`` must already be populated by the caller
        (typically via the equipment's ``prefetch_forecasts``).

        :param model: The optimisation model.
        :param parameters: Module parameters (unused — accepted for signature symmetry
            with other dispatch classes).
        """
        del parameters
        self._model = model
        n = self._eq.name
        self.power_level_var = ModelVar(
            getter=lambda time: model.get_variable(f"{n}_power_level_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{n}_power_level_{time}", lower_bound=0, upper_bound=self.max_power(time)
            ),
        )

    def add_variables(self, time: DateTime) -> None:
        """Register the power-level variable for *time* in the model."""
        self.power_level_var.set_model_var(time)

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

        power_level_var = self.power_level_var.get_value(time)
        model.add_constraint(power_level_var <= max_p, f"power_max_{time}_{n}")
        model.add_constraint(power_level_var >= min_p, f"power_min_{time}_{n}")

    def max_power(self, time: DateTime) -> float:
        """Forecast-driven upper bound on power, or 0 when no forecast is cached."""
        forecast = self._eq._cached_forecast
        return forecast.get_value(time) if forecast else 0.0

    def min_power(self, time: DateTime) -> float:
        """Curtailment-driven lower bound: ``(1 - curtailment_ratio) × max_power``."""
        return (1 - self._eq.maximum_curtailment_ratio.get_value(time)) * self.max_power(time)
