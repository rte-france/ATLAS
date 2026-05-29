"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pendulum import DateTime

from atlas.common.optimal_dispatch.reserves.handler import ReserveHandler

if TYPE_CHECKING:
    from atlas.common.optimal_dispatch.dispatch.thermal import ThermalDispatch


class ThermalReserveHandler(ReserveHandler):
    """
    Reserve handler for thermal equipment.

    Declares thermal-specific variables (including ``relaxed_reserves``) and
    implements all reserve constraints that rely on :class:`ThermalDispatch`
    state variables.

    Instantiate via :meth:`ReserveFactory.for_thermal`, not directly.
    """

    def __init__(self, name: str, dispatch: ThermalDispatch, maximum_automated: float) -> None:
        super().__init__(name, maximum_automated)
        self._dispatch = dispatch

    def add_variables(self, time: DateTime, max_power: float, min_power: float) -> None:
        m = self._require_model()
        m.add_continuous_variable(self.var("reserves_up", time), 0, max_power)
        m.add_continuous_variable(self.var("reserves_down", time), 0, max_power)
        m.add_continuous_variable(self.var("unprovided_reserves_up", time), 0, max_power)
        m.add_continuous_variable(self.var("unprovided_reserves_down", time), 0, max_power)
        m.add_continuous_variable(self.var("relaxed_reserves", time), 0, min_power)
        m.add_continuous_variable(self.var("automated_reserves_up", time), 0, self._maximum_automated)
        m.add_continuous_variable(self.var("automated_reserves_down", time), 0, self._maximum_automated)

    def add_fill_up_constraints(
        self,
        time: DateTime,
        power_var,
        max_power: float,
        min_power: float,
        epsilon: float,
    ) -> None:
        """
        Add fill-up equality constraints (up and down) at *time*.

        Up:   ``power + reserves_up + automated_reserves_up + unprovided_reserves_up ≈ max_power``

        Down: ``power - reserves_down - automated_reserves_down - unprovided_reserves_down
               + relaxed_reserves ≈ min_power``

        :param time: Timestep
        :type time: DateTime
        :param power_var: LP variable for power level at *time*
        :param max_power: Maximum power at *time*
        :type max_power: float
        :param min_power: Minimum power at *time*
        :type min_power: float
        :param epsilon: Allowed round-off tolerance
        :type epsilon: float
        """
        m = self._require_model()
        ru = m.get_variable(self.var("reserves_up", time))
        aru = m.get_variable(self.var("automated_reserves_up", time))
        uru = m.get_variable(self.var("unprovided_reserves_up", time))
        rd = m.get_variable(self.var("reserves_down", time))
        ard = m.get_variable(self.var("automated_reserves_down", time))
        urd = m.get_variable(self.var("unprovided_reserves_down", time))
        rr = m.get_variable(self.var("relaxed_reserves", time))

        n = self._name
        up_sum = power_var + ru + aru + uru
        m.add_constraint(up_sum <= max_power + epsilon, f"up_fillup_1_{time}_{n}")
        m.add_constraint(up_sum >= max_power - epsilon, f"up_fillup_2_{time}_{n}")

        down_sum = power_var - rd - ard - urd + rr
        m.add_constraint(down_sum <= min_power + epsilon, f"down_fillup_1_{time}_{n}")
        m.add_constraint(down_sum >= min_power - epsilon, f"down_fillup_2_{time}_{n}")

    def add_relaxed_reserve_constraint(self, time: DateTime, min_power: float) -> None:
        """
        Add the relaxed-reserve upper-bound constraint at *time*.

        Forces ``relaxed_reserves ≤ min_power × (1 − online)``, where *online* sums
        ``on_up``, ``on_down`` and, when applicable, ``on_flat``.

        :param time: Timestep
        :type time: DateTime
        :param min_power: Minimum power at *time*
        :type min_power: float
        """
        m = self._require_model()
        d = self._dispatch
        online_sum = d.on_up_var.get_value(time) + d.on_down_var.get_value(time)
        if d._has_flat:
            online_sum = online_sum + d.on_flat_var.get_value(time)
        m.add_constraint(
            m.get_variable(self.var("relaxed_reserves", time)) <= min_power * (1 - online_sum),
            f"relaxed_reserves_{time}_{self._name}",
        )

    def add_capacity_constraints(self, time: DateTime, max_power: float) -> None:
        """
        Add reserve capacity constraints at *time*.

        Automated reserves are zeroed when the unit is unavailable (off / starting / stopping).
        Manual reserves are additionally zeroed during ramp phases when ``_has_flat`` is set.

        :param time: Timestep
        :type time: DateTime
        :param max_power: Maximum power at *time*
        :type max_power: float
        """
        m = self._require_model()
        d = self._dispatch

        unavailable = d.off_var.get_value(time)
        if d._has_start:
            unavailable = unavailable + d.on_start_var.get_value(time)
        if d._has_stop:
            unavailable = unavailable + d.stop_var.get_value(time)

        n = self._name
        aru = m.get_variable(self.var("automated_reserves_up", time))
        ard = m.get_variable(self.var("automated_reserves_down", time))
        m.add_constraint(aru <= self._maximum_automated * (1 - unavailable), f"automated_reserves_up_max_{time}_{n}")
        m.add_constraint(ard <= self._maximum_automated * (1 - unavailable), f"automated_reserves_down_max_{time}_{n}")

        res_unavailable = unavailable
        if d._has_flat:
            res_unavailable = res_unavailable + d.on_up_var.get_value(time) + d.on_down_var.get_value(time)

        ru = m.get_variable(self.var("reserves_up", time))
        rd = m.get_variable(self.var("reserves_down", time))
        m.add_constraint(ru <= max_power * (1 - res_unavailable), f"reserves_up_max_{time}_{n}")
        m.add_constraint(rd <= max_power * (1 - res_unavailable), f"reserves_down_max_{time}_{n}")
