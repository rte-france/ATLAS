"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.common.optimal_dispatch.reserves.handler import ReserveHandler

if TYPE_CHECKING:
    from pendulum import DateTime


class RenewableReserveHandler(ReserveHandler):
    """
    Reserve handler for renewable (wind / solar) equipment.

    Declares the standard reserve set (manual up/down, automated up/down, unprovided up/down)
    without the thermal-specific ``relaxed_reserves`` variable. Variable bounds and capacity
    constraints are kept explicit (redundant with bounds, but emitted for LP-parity with the
    prior step formulation).

    Instantiate via :meth:`ReserveFactory.for_renewable`, not directly.
    """

    def add_variables(self, time: DateTime, max_power: float, min_power: float) -> None:
        m = self._require_model()
        m.add_continuous_variable(self.var("reserves_up", time), 0, max_power)
        m.add_continuous_variable(self.var("reserves_down", time), min_power, max_power)
        m.add_continuous_variable(self.var("unprovided_reserves_up", time), 0, max_power)
        m.add_continuous_variable(self.var("unprovided_reserves_down", time), min_power, max_power)
        m.add_continuous_variable(self.var("automated_reserves_up", time), 0, self._maximum_automated)
        m.add_continuous_variable(self.var("automated_reserves_down", time), 0, self._maximum_automated)

    def add_capacity_constraints(self, time: DateTime, max_power: float) -> None:
        """
        Add the manual reserve capacity bounds at *time*.

        ``reserves_up ≤ max_power``  and  ``reserves_down ≤ max_power``.
        Redundant with variable upper bounds — emitted for LP-parity.
        """
        m = self._require_model()
        n = self._name
        m.add_constraint(m.get_variable(self.var("reserves_up", time)) <= max_power, f"reserves_up_max_{time}_{n}")
        m.add_constraint(m.get_variable(self.var("reserves_down", time)) <= max_power, f"reserves_down_max_{time}_{n}")

    def add_automated_capacity_constraints(self, time: DateTime) -> None:
        """
        Add the automated reserve capacity bounds at *time*.

        ``automated_reserves_up ≤ maximum_automated``  and  ``automated_reserves_down ≤ maximum_automated``.
        Redundant with variable upper bounds — emitted for LP-parity.
        """
        m = self._require_model()
        n = self._name
        m.add_constraint(
            m.get_variable(self.var("automated_reserves_up", time)) <= self._maximum_automated,
            f"automated_reserves_up_max_{time}_{n}",
        )
        m.add_constraint(
            m.get_variable(self.var("automated_reserves_down", time)) <= self._maximum_automated,
            f"automated_reserves_down_max_{time}_{n}",
        )
