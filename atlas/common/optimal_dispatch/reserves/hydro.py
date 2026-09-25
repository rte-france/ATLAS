"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.common.optimal_dispatch.reserves.renewable import RenewableReserveHandler

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.common.optimal_dispatch.dispatch.hydro import HydroDispatch


class HydroReserveHandler(RenewableReserveHandler):
    """
    Reserve handler for hydro reservoir equipment.

    Hydro reservoirs share the same standard reserve variable shape as wind/solar (manual
    up/down, automated up/down, unprovided up/down) plus two specifics:

    - A ``relaxed_reserves`` variable bounded by ``[min_power, 0]`` to absorb infeasibility
      when the reservoir cannot supply at its declared minimum power.
    - Storage-level coupling constraints linking the stored-energy state variable with the
      reserved capacity.

    The shared variable shape and the basic capacity bounds are inherited from
    :class:`RenewableReserveHandler` — only the hydro-specific extensions are declared here.

    Instantiate via :meth:`ReserveFactory.for_hydro`, not directly.
    """

    def __init__(self, name: str, dispatch: HydroDispatch, maximum_automated: float) -> None:
        super().__init__(name, maximum_automated)
        self._dispatch = dispatch

    def add_variables(self, time: DateTime, max_power: float, min_power: float) -> None:
        super().add_variables(time, max_power, min_power)
        self._require_model().add_continuous_variable(self.var("relaxed_reserves", time), min_power, 0)

    def add_relaxed_reserve_constraint(self, time: DateTime, min_power: float) -> None:
        """``relaxed_reserves ≤ min_power``."""
        m = self._require_model()
        m.add_constraint(
            m.get_variable(self.var("relaxed_reserves", time)) <= min_power, f"relaxed_reserves_{time}_{self._name}"
        )

    def add_storage_level_constraints(self, time: DateTime, min_energy: float, max_energy: float) -> None:
        """
        Couple the stored-energy state with reserves at *time*.

        ``stored_energy ≥ min_energy + reserves_up + automated_reserves_up``

        ``stored_energy ≤ max_energy − reserves_down − automated_reserves_down``
        """
        m = self._require_model()
        n = self._name
        stored = self._dispatch.stored_energy_var.get_value(time)
        ru = m.get_variable(self.var("reserves_up", time))
        aru = m.get_variable(self.var("automated_reserves_up", time))
        rd = m.get_variable(self.var("reserves_down", time))
        ard = m.get_variable(self.var("automated_reserves_down", time))

        m.add_constraint(stored >= min_energy + ru + aru, f"min_storage_level_{time}_{n}")
        m.add_constraint(stored <= max_energy - rd - ard, f"max_storage_level_{time}_{n}")
