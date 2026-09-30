"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.common.optimal_dispatch.marginal_pricing import bid_volumes
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pendulum import DateTime

    from atlas.abstract_class.parameters import AbstractModuleParameters
    from atlas.common.optimal_dispatch.input_objects.hydro import HydroDispatchInput
    from atlas.solver.temporal_variable import TemporalVariable


class HydroDispatch:
    """
    Physical dispatch component for a single hydro reservoir unit.

    Owns:

    - ``{name}_stored_energy`` — reservoir energy state per timestep, bounded by
      ``[0, max_energy(time)]``.
    - ``{name}_power_level_frag_{category}`` — one fragment per piecewise-linear
      bid segment large enough to offer (see :func:`~atlas.common.optimal_dispatch.marginal_pricing.bid_volumes`),
      bounded by its (possibly redistributed) volume.

    Provides the energy-balance constraint (``stored_energy = previous + inflow − Σ fragments × Δt``),
    which the caller invokes only at the dates when balance applies (e.g. PO portfolio_time_window).

    Does **not** handle reserves, storage-level reserve coupling, marginal-value pricing,
    or the objective function — those are handled by :class:`HydroReserveHandler` and
    the calling module's step.

    Typical usage::

        dispatch = HydroDispatch(equipment)
        dispatch.setup(model, parameters)
        dispatch.add_variables(time_window)
        for time in portfolio_time_window:
            dispatch.add_energy_balance(model, time, parameters)
    """

    def __init__(self, equipment: HydroDispatchInput) -> None:
        self._eq = equipment
        self.stored_energy: TemporalVariable
        self.power_level_frag: dict[int, TemporalVariable] = {}
        self._minimal_fragment_size: float = 0.0
        self._fragment_volumes: dict[DateTime, dict[int, float]] = {}

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters) -> None:
        """Bind to a solver model and declare the stored-energy and fragment temporal variables."""
        self._minimal_fragment_size = parameters.hydraulic_minimal_fragment_size  # type: ignore[attr-defined]
        self._fragment_volumes = {}
        eq = self._eq
        n = eq.name
        self.stored_energy = model.add_temporal_variable(
            f"{n}_stored_energy", lower_bound=0, upper_bound=eq.maximum_energy
        )
        self.power_level_frag = {
            category: model.add_temporal_variable(
                f"{n}_power_level_frag_{category}",
                lower_bound=0,
                upper_bound=lambda time, category=category: self.fragment_volumes(time)[category],
            )
            for category in eq.fragment_data
        }

    def add_variables(self, times: Iterable[DateTime]) -> None:
        """
        Register the stored-energy and fragment power variables for *times*.

        A fragment only gets a variable at the timesteps where it is kept by :meth:`fragment_volumes`.
        """
        times = list(times)
        self.stored_energy.add_all(times)
        for category, fragment in self.power_level_frag.items():
            fragment.add_all(time for time in times if category in self.fragment_volumes(time))

    def fragment_volumes(self, time: DateTime) -> dict[int, float]:
        """Return the volume of each fragment kept at *time*, keyed by category."""
        if time not in self._fragment_volumes:
            eq = self._eq
            self._fragment_volumes[time] = bid_volumes(
                eq.fragment_data, eq.maximum_power.get_value(time), self._minimal_fragment_size
            )
        return self._fragment_volumes[time]

    def power_fragments_sum(self, time: DateTime):
        """Return the symbolic sum of the fragment power variables kept at *time*."""
        return sum(self.power_level_frag[k][time] for k in self.fragment_volumes(time))

    def add_energy_balance(
        self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters
    ) -> None:
        """
        Add the reservoir energy-balance constraint at *time*.

        ``stored_energy[t] = stored_energy[t − Δt] − Σ fragments × Δt + inflow``

        At ``t = start_date``, ``stored_energy[t − Δt]`` is replaced by ``initial_level``.
        Inflow uses the timestep's *day* fraction since the source series is daily.

        Should be invoked only at the timesteps where balance applies (e.g. PO portfolio_time_window).
        """
        eq = self._eq
        n = eq.name
        ts = parameters.temporal.timestep
        start = parameters.temporal.start_date
        dt_h = ts.total_hours()
        dt_d = ts.total_days()

        inflow = eq.inflows.get_value(time) * dt_d if eq.inflows is not None else 0.0
        power_sum = self.power_fragments_sum(time)
        stored = self.stored_energy[time]

        if time == start:
            initial = eq.initial_level.get_value(start - ts)
            model.add_constraint(stored == initial - power_sum * dt_h + inflow, f"storage_level_evol_{time}_{n}")
        else:
            stored_prev = self.stored_energy[time - ts]
            model.add_constraint(stored == stored_prev - power_sum * dt_h + inflow, f"storage_level_evol_{time}_{n}")
