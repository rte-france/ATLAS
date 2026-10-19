"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.common.optimal_dispatch.reserves.handler import ReserveHandler

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pendulum import DateTime

    from atlas.solver.temporal_variable import Bound


class StorageReserveHandler(ReserveHandler):
    """
    Reserve handler for storage equipment.

    Declares storage-specific variables (bidirectional ``automated_reserves_down``)
    and implements fill-up and SOC-based capacity constraints.

    Instantiate via :meth:`ReserveFactory.for_storage`, not directly.
    """

    def add_variables(self, times: Iterable[DateTime], max_power: Bound, min_power: Bound) -> None:
        """
        :param min_power: Minimum power of the storage unit — expected to be *negative*
            (charging draws power from the grid). Used as lower bound for down-reserve
            variables to preserve the same LP bounds as the original formulation.
        """
        times = list(times)
        self.reserves_up = self._declare("reserves_up", times, 0, max_power)
        self.reserves_down = self._declare("reserves_down", times, min_power, max_power)
        self.unprovided_reserves_up = self._declare("unprovided_reserves_up", times, 0, max_power)
        self.unprovided_reserves_down = self._declare("unprovided_reserves_down", times, min_power, max_power)
        self.automated_reserves_up = self._declare("automated_reserves_up", times, 0, self._maximum_automated)
        # bidirectional: storage can provide automated down-reserve in either direction
        self.automated_reserves_down = self._declare(
            "automated_reserves_down", times, -self._maximum_automated, self._maximum_automated
        )

    def add_bound_constraints(self, time: DateTime, max_power: float) -> None:
        """
        Add explicit upper-bound constraints on reserve variables at *time*.

        These four constraints cap each reserve variable at its physical limit,
        preserving the original LP formulation:

        - ``automated_reserves_up ≤ maximum_automated``
        - ``automated_reserves_down ≤ maximum_automated``
        - ``reserves_up ≤ max_power``
        - ``reserves_down ≤ max_power``
        """
        m = self._require_model()
        aru = self.automated_reserves_up[time]
        ard = self.automated_reserves_down[time]
        ru = self.reserves_up[time]
        rd = self.reserves_down[time]

        m.add_constraint(aru <= self._maximum_automated, f"automated_reserves_up_max_{time}_{self._name}")
        m.add_constraint(ard <= self._maximum_automated, f"automated_reserves_down_max_{time}_{self._name}")
        m.add_constraint(ru <= max_power, f"reserves_up_max_{time}_{self._name}")
        m.add_constraint(rd <= max_power, f"reserves_down_max_{time}_{self._name}")

    def add_fill_up_constraints(
        self,
        time: DateTime,
        power_sell_var,
        power_buy_var,
        max_sell: float,
        min_buy: float,
    ) -> None:
        """
        Add fill-up inequality constraints at *time*.

        Up:   ``power_sell + reserves_up + automated_reserves_up + unprovided_reserves_up ≤ max_sell``

        Down: ``power_buy − reserves_down − automated_reserves_down − unprovided_reserves_down ≥ min_buy``

        :param time: Timestep
        :type time: DateTime
        :param power_sell_var: LP variable for sell (discharge) power at *time*
        :param power_buy_var: LP variable for buy (charge) power at *time* (negative convention)
        :param max_sell: Effective maximum sell capacity (accounting for efficiency and v2g)
        :type max_sell: float
        :param min_buy: Effective minimum buy capacity (negative, accounting for efficiency)
        :type min_buy: float
        """
        m = self._require_model()
        ru = self.reserves_up[time]
        aru = self.automated_reserves_up[time]
        uru = self.unprovided_reserves_up[time]
        rd = self.reserves_down[time]
        ard = self.automated_reserves_down[time]
        urd = self.unprovided_reserves_down[time]

        m.add_constraint(
            power_sell_var + ru + aru + uru <= max_sell,
            f"generic_power_max_{time}_{self._name}",
        )
        m.add_constraint(
            power_buy_var - rd - ard - urd >= min_buy,
            f"generic_power_min_{time}_{self._name}",
        )

    def add_capacity_constraints(
        self,
        time: DateTime,
        stored_energy_var,
        max_energy: float,
        min_soc: float,
        reserve_duration_h: float,
        automated_reserve_duration_h: float,
    ) -> None:
        """
        Add SOC-based reserve capacity constraints at *time*.

        Ensures the stored energy remains sufficient to honour committed reserves
        for their declared duration:

        ``stored_energy ≥ min_soc × max_energy + reserve_soc_up``

        ``stored_energy ≤ max_energy − reserve_soc_down``

        where ``reserve_soc_up/down = manual_reserve × reserve_duration
        + automated_reserve × automated_reserve_duration``.

        :param time: Timestep
        :type time: DateTime
        :param stored_energy_var: LP variable for stored energy at *time*
        :param max_energy: Maximum storable energy at *time* (MWh)
        :type max_energy: float
        :param min_soc: Minimum state of charge coefficient at *time*
        :type min_soc: float
        :param reserve_duration_h: Duration of manual reserves (hours)
        :type reserve_duration_h: float
        :param automated_reserve_duration_h: Duration of automated reserves (hours)
        :type automated_reserve_duration_h: float
        """
        m = self._require_model()
        ru = self.reserves_up[time]
        aru = self.automated_reserves_up[time]
        rd = self.reserves_down[time]
        ard = self.automated_reserves_down[time]

        reserve_soc_up = ru * reserve_duration_h + aru * automated_reserve_duration_h
        reserve_soc_down = rd * reserve_duration_h + ard * automated_reserve_duration_h

        m.add_constraint(
            stored_energy_var >= max_energy * min_soc + reserve_soc_up,
            f"min_storage_level_{time}_{self._name}",
        )
        m.add_constraint(
            stored_energy_var <= max_energy - reserve_soc_down,
            f"max_storage_level_{time}_{self._name}",
        )
