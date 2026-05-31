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
    from atlas.common.optimal_dispatch.input_objects.hydro import HydroDispatchInput


class HydroDispatch:
    """
    Physical dispatch component for a single hydro reservoir unit.

    Owns:

    - ``{name}_stored_energy_{time}`` — reservoir energy state per timestep, bounded by
      ``[0, max_energy(time)]``.
    - ``{name}_power_level_frag_{category}_{time}`` — one fragment per piecewise-linear
      bid segment (defined by ``equipment.fragment_data``), bounded by the segment volume.

    Provides the energy-balance constraint (``stored_energy = previous + inflow − Σ fragments × Δt``),
    which the caller invokes only at the dates when balance applies (e.g. PO target times).

    Does **not** handle reserves, storage-level reserve coupling, marginal-value pricing,
    or the objective function — those are handled by :class:`HydroReserveHandler` and
    the calling module's step.

    Typical usage::

        dispatch = HydroDispatch(equipment)
        dispatch.setup(model, parameters)
        for time in time_window:
            dispatch.add_variables(time)
        for time in target_times:
            dispatch.add_energy_balance(model, time, parameters)
    """

    def __init__(self, equipment: HydroDispatchInput) -> None:
        self._eq = equipment
        self._model: OptimisationModel = None  # type: ignore[assignment]
        self.stored_energy_var: ModelVar = None  # type: ignore[assignment]

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters) -> None:
        """Bind to a solver model and prepare the stored-energy variable handle."""
        del parameters
        self._model = model
        eq = self._eq
        n = eq.name
        self.stored_energy_var = ModelVar(
            getter=lambda time: model.get_variable(f"{n}_stored_energy_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{n}_stored_energy_{time}", lower_bound=0, upper_bound=eq.maximum_energy.get_value(time)
            ),
        )

    def add_variables(self, time: DateTime) -> None:
        """Register the stored-energy and fragment power variables for *time*."""
        self.stored_energy_var.set_model_var(time)
        eq = self._eq
        max_p_t = eq.maximum_power.get_value(time)
        for category, fragment in eq.fragment_data.items():
            volume = max_p_t * fragment.volume
            self._model.add_continuous_variable(self._frag_key(time, category), lower_bound=0, upper_bound=volume)

    def power_fragments_sum(self, time: DateTime):
        """Return the symbolic sum of all fragment power variables at *time*."""
        return sum(self._model.get_variable(self._frag_key(time, k)) for k in self._eq.fragment_data)

    def get_fragment_var(self, time: DateTime, category: int):
        """Return the fragment power variable for *category* at *time*."""
        return self._model.get_variable(self._frag_key(time, category))

    def add_energy_balance(
        self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters
    ) -> None:
        """
        Add the reservoir energy-balance constraint at *time*.

        ``stored_energy[t] = stored_energy[t − Δt] − Σ fragments × Δt + inflow``

        At ``t = start_date``, ``stored_energy[t − Δt]`` is replaced by ``initial_level``.
        Inflow uses the timestep's *day* fraction since the source series is daily.

        Should be invoked only at the timesteps where balance applies (e.g. PO target_times).
        """
        eq = self._eq
        n = eq.name
        ts = parameters.temporal.timestep
        start = parameters.temporal.start_date
        dt_h = ts.total_hours()
        dt_d = ts.total_days()

        inflow = eq.inflows.get_value(time) * dt_d if eq.inflows is not None else 0.0
        power_sum = self.power_fragments_sum(time)
        stored = self.stored_energy_var.get_value(time)

        if time == start:
            initial = eq.initial_level.get_value(start - ts)
            model.add_constraint(stored == initial - power_sum * dt_h + inflow, f"storage_level_evol_{time}_{n}")
        else:
            stored_prev = self.stored_energy_var.get_value(time - ts)
            model.add_constraint(stored == stored_prev - power_sum * dt_h + inflow, f"storage_level_evol_{time}_{n}")

    def _frag_key(self, time: DateTime, category: int) -> str:
        return f"{self._eq.name}_power_level_frag_{category}_{time}"
