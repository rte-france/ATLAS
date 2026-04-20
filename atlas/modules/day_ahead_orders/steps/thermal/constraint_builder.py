"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pendulum import DateTime

import atlas.config as cfg

if TYPE_CHECKING:
    from atlas.modules.day_ahead_orders.steps.thermal.thermal_optimization_model import ThermalOptimizationModel


class ThermalConstraintBuilder:
    """
    Builds the full constraint set for a ThermalOptimizationModel based on T_start, T_stop,
    and T_stable. Replaces the 8 combination_*.py files with conditional composition.

    The 8 original combinations mapped to (T_stop >= 1, T_start >= 1, T_stable >= 1):
        1: (0, 0, 0)   2: (1, 0, 0)   3: (0, 0, 1)   4: (0, 1, 0)
        5: (1, 0, 1)   6: (0, 1, 1)   7: (1, 1, 0)   8: (1, 1, 1)
    """

    def __init__(self, model: "ThermalOptimizationModel") -> None:
        self._m = model
        self._has_stop = model.T_stop >= 1
        self._has_start = model.T_start >= 1
        self._has_flat = model.T_stable >= 1
        # Local auxiliaries created conditionally
        self._down_to_stop: dict[DateTime, Any] = {}  # T_stop >= 1, T_stable == 0
        self._flat_down_stop: dict[DateTime, Any] = {}  # T_stop >= 1, T_stable >= 1
        self._DD: dict[DateTime, Any] = {}  # T_stop >= 1, T_stable >= 1

    def build(self, day_zero: bool) -> None:
        """Add all initial conditions and constraints to the model."""
        self._create_local_auxiliaries()
        self._set_initial_conditions(day_zero)
        self._add_auxiliary_variable_constraints()
        self._add_state_variable_constraints()
        self._add_control_variable_constraints()
        self._add_daily_energy_constraint()

    def _create_local_auxiliaries(self) -> None:
        m = self._m
        if self._has_stop and not self._has_flat:
            # eq. (20) — tracks ON_DOWN → STOP transition
            for t in m.time_frame:
                self._down_to_stop[t] = m.add_continuous_variable(
                    f"down_to_stop_equip_{m.thermal_unit.name}_at_{t}", 0, 1
                )
        if self._has_stop and self._has_flat:
            # eq. (22) — tracks FLAT → DOWN → STOP path
            for t in m.time_frame:
                self._flat_down_stop[t] = m.add_continuous_variable(
                    f"flat_down_stop_at_{t}_equip_{m.thermal_unit.name}", 0, 1
                )
            # eq. (23) — gradient correction for DOWN → STOP
            # Comb 5 (no_start): DD_at_{t}_equip_{name}; comb 8 (has_start): DD_{t}_equip_{name}
            dd_prefix = "DD" if self._has_start else "DD_at"
            for t in m.gradients_time_frame:
                self._DD[t] = m.add_continuous_variable(
                    f"{dd_prefix}_{t}_equip_{m.thermal_unit.name}", m.Q_min, m.Q_max
                )

    def _set_initial_conditions(self, day_zero: bool) -> None:
        if day_zero:
            self._init_day_zero()
        else:
            self._init_from_previous()
        if self._has_flat:
            self._init_gradient_auxiliaries()

    def _init_day_zero(self) -> None:
        m = self._m
        cfg.logger.debug(f"Initial conditions of unit {m.thermal_unit.name} have been set as in equation (47).")
        for t in m.previous_time_frame:
            m.q.set_extended(t, 0)
            m.OFF.set_extended(t, 1)
            m.ON_UP.set_extended(t, 0)
            m.ON_DOWN.set_extended(t, 0)
            if self._has_stop:
                m.STOP.set_extended(t, 0)
            if self._has_start:
                m.START.set_extended(t, 0)
            if self._has_flat and t != m.start_date_minus_one:
                m.ON_FLAT.set_extended(t, 0)
                m.stable.set_extended(t, 0)
                m.entered_up.set_extended(t, 0)
                m.entered_down.set_extended(t, 0)
            m.turned_on.set_extended(t, 0)
            m.turned_off.set_extended(t, 0)
            if t in self._down_to_stop:
                self._down_to_stop[t] = 0
            if t in self._flat_down_stop:
                self._flat_down_stop[t] = 0

    def _init_from_previous(self) -> None:
        m = self._m
        for t in m.previous_time_frame:
            m.q.set_extended(t, int(m.last_power.get_value(t)))
        self._init_state_variables_from_previous()
        if self._has_start and self._has_stop:
            self._distinguish_start_stop()
        self._init_auxiliaries_from_previous()
        if self._has_flat:
            self._init_on_up_down_flat_from_previous()
            self._init_stable_entered_from_previous()
        if self._has_stop and self._has_flat:
            self._init_flat_down_stop_from_previous()

    def _init_state_variables_from_previous(self) -> None:
        m = self._m
        for t in m.previous_time_frame:
            q = m.last_power.get_value(t)
            q_min = m.thermal_unit.minimum_power.get_value(t)

            if self._has_start or self._has_stop:
                if q >= q_min:
                    m.OFF.set_extended(t, 0)
                    if self._has_stop:
                        m.STOP.set_extended(t, 0)
                    if self._has_start:
                        m.START.set_extended(t, 0)
                    if not self._has_flat:
                        # No stable constraint — allow unit full flexibility
                        m.ON_DOWN.set_extended(t, 1)
                        m.ON_UP.set_extended(t, 1)
                elif q > 0:
                    m.OFF.set_extended(t, 0)
                    if self._has_stop:
                        m.STOP.set_extended(t, 1)
                    if self._has_start:
                        # Both tentatively set to 1; _distinguish_start_stop resolves ambiguity
                        m.START.set_extended(t, 1)
                    if not self._has_flat:
                        m.ON_UP.set_extended(t, 0)
                        m.ON_DOWN.set_extended(t, 0)
                    elif t != m.start_date_minus_one:
                        m.ON_UP.set_extended(t, 0)
                        m.ON_DOWN.set_extended(t, 0)
                        m.ON_FLAT.set_extended(t, 0)
                else:
                    m.OFF.set_extended(t, 1)
                    if self._has_stop:
                        m.STOP.set_extended(t, 0)
                    if self._has_start:
                        m.START.set_extended(t, 0)
                    if not self._has_flat:
                        m.ON_UP.set_extended(t, 0)
                        m.ON_DOWN.set_extended(t, 0)
                    elif t != m.start_date_minus_one:
                        m.ON_UP.set_extended(t, 0)
                        m.ON_DOWN.set_extended(t, 0)
                        m.ON_FLAT.set_extended(t, 0)
            else:
                # Combinations 1 and 3: no ramp states
                if q > 0:
                    m.OFF.set_extended(t, 0)
                    if not self._has_flat:
                        m.ON_DOWN.set_extended(t, 1)
                        m.ON_UP.set_extended(t, 1)
                    # has_flat: ON_UP/DOWN/FLAT set later by reconstruction
                else:
                    m.OFF.set_extended(t, 1)
                    if not self._has_flat:
                        m.ON_UP.set_extended(t, 0)
                        m.ON_DOWN.set_extended(t, 0)
                    elif t != m.start_date_minus_one:
                        m.ON_UP.set_extended(t, 0)
                        m.ON_DOWN.set_extended(t, 0)
                        m.ON_FLAT.set_extended(t, 0)

    def _distinguish_start_stop(self) -> None:
        """Resolve ambiguous ramp states using power trajectory (combinations 7 and 8)."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.previous_time_frame[:-1]:
            t_prev = t - ts
            if m.START.get_extended_value(t) == 1:
                if m.q.get_extended_value(t) > m.q.get_extended_value(t_prev):
                    m.STOP.set_extended(t, 0)
                    m.START.set_extended(t, 1)
                elif m.q.get_extended_value(t) < m.q.get_extended_value(t_prev):
                    m.STOP.set_extended(t, 1)
                    m.START.set_extended(t, 0)

    def _init_auxiliaries_from_previous(self) -> None:
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.previous_time_frame:
            m.turned_on.set_extended(t, 0)
            m.turned_off.set_extended(t, 0)
            if t in self._down_to_stop:
                self._down_to_stop[t] = 0

            if t == m.extended_start_date:
                continue
            t_prev = t - ts

            # turned_off: entering STOP (if has_stop) or entering OFF
            if self._has_stop:
                if m.STOP.get_extended_value(t) - m.STOP.get_extended_value(t_prev) == 1:
                    m.turned_off.set_extended(t, 1)
            else:
                if m.OFF.get_extended_value(t) - m.OFF.get_extended_value(t_prev) == 1:
                    m.turned_off.set_extended(t, 1)

            # turned_on: entering START (if has_start) or leaving OFF
            if self._has_start:
                if m.START.get_extended_value(t) - m.START.get_extended_value(t_prev) == 1:
                    m.turned_on.set_extended(t, 1)
            else:
                if m.OFF.get_extended_value(t) - m.OFF.get_extended_value(t_prev) == -1:
                    m.turned_on.set_extended(t, 1)

            # down_to_stop: detect ON_DOWN → STOP transition (eq. 20)
            if self._down_to_stop and t in self._down_to_stop:
                if m.STOP.get_extended_value(t) - m.ON_DOWN.get_extended_value(t_prev) == 0:
                    self._down_to_stop[t] = 1

    def _init_on_up_down_flat_from_previous(self) -> None:
        """Reconstruct ON_UP, ON_DOWN, ON_FLAT from the power trajectory (T_stable >= 1)."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.previous_time_frame[:-1]:
            t_prev = t - ts
            # Combination 6 (T_start + T_stable): use q >= q_min to exclude START state
            # Other flat combinations: use OFF == 0
            if self._has_start:
                is_fully_online = m.q.get_extended_value(t_prev) >= m.thermal_unit.minimum_power.get_value(t_prev)
            else:
                is_fully_online = m.OFF.get_extended_value(t_prev) == 0

            if is_fully_online:
                q_t = m.q.get_extended_value(t)
                q_t_prev = m.q.get_extended_value(t_prev)
                if q_t > q_t_prev:
                    m.ON_UP.set_extended(t_prev, 1)
                    m.ON_DOWN.set_extended(t_prev, 0)
                    m.ON_FLAT.set_extended(t_prev, 0)
                elif q_t < q_t_prev:
                    m.ON_UP.set_extended(t_prev, 0)
                    m.ON_DOWN.set_extended(t_prev, 1)
                    m.ON_FLAT.set_extended(t_prev, 0)
                else:
                    m.ON_UP.set_extended(t_prev, 0)
                    m.ON_DOWN.set_extended(t_prev, 0)
                    m.ON_FLAT.set_extended(t_prev, 1)
            else:
                m.ON_UP.set_extended(t_prev, 0)
                m.ON_DOWN.set_extended(t_prev, 0)
                m.ON_FLAT.set_extended(t_prev, 0)

    def _init_stable_entered_from_previous(self) -> None:
        """Initialize stable, entered_up, entered_down auxiliaries (T_stable >= 1)."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.previous_time_frame[1:]:
            m.stable.set_extended(t, 0)
            m.entered_up.set_extended(t, 0)
            m.entered_down.set_extended(t, 0)
            if t == m.extended_start_date or m.OFF.get_extended_value(t) == 1:
                continue
            t_prev = t - ts
            if m.ON_FLAT.get_extended_value(t) - m.ON_FLAT.get_extended_value(t_prev) == 1:
                m.stable.set_extended(t, 1)
            if m.ON_UP.get_extended_value(t) - m.ON_UP.get_extended_value(t_prev) == 1:
                m.entered_up.set_extended(t, 1)
            if m.ON_DOWN.get_extended_value(t) - m.ON_DOWN.get_extended_value(t_prev) == 1:
                m.entered_down.set_extended(t, 1)

    def _init_flat_down_stop_from_previous(self) -> None:
        """Initialize flat_down_stop auxiliary (T_stop >= 1, T_stable >= 1)."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.previous_time_frame[:-2]:
            t_minus_one = t - ts
            t_minus_two = t - 2 * ts
            self._flat_down_stop[t] = int(
                math.floor(
                    (
                        m.STOP.get_extended_value(t)
                        + m.ON_DOWN.get_extended_value(t_minus_one)
                        + m.ON_FLAT.get_extended_value(t_minus_two)
                    )
                    / 3
                )
            )

    def _init_gradient_auxiliaries(self) -> None:
        """Initialize U and D at start_date_minus_one (T_stable >= 1)."""
        m = self._m
        ts = m.parameters.temporal.timestep
        start_date_minus_two = m.parameters.temporal.start_date - 2 * ts
        m.U.set_extended(
            m.start_date_minus_one,
            m.ON_UP.get_value(m.start_date_minus_one)
            * m.ON_UP.get_value(start_date_minus_two)
            * (m.q.get_extended_value(m.start_date_minus_one) - m.q.get_extended_value(start_date_minus_two)),
        )
        m.D.set_extended(
            m.start_date_minus_one,
            m.ON_DOWN.get_value(m.start_date_minus_one)
            * m.ON_DOWN.get_value(start_date_minus_two)
            * (m.q.get_extended_value(m.start_date_minus_one) - m.q.get_extended_value(start_date_minus_two)),
        )

    # ──────────────────────────────────────────────────────────────────────
    # Auxiliary variable constraints (Section B in original files)
    # ──────────────────────────────────────────────────────────────────────

    def _add_auxiliary_variable_constraints(self) -> None:
        self._add_turned_on_constraints()
        self._add_turned_off_constraints()
        if self._has_flat:
            self._add_stable_constraints()
            if self._flat_down_stop:
                self._add_flat_down_stop_constraints()
            self._add_entered_up_down_constraints()
            self._add_ud_gradient_auxiliary_constraints()
        if self._down_to_stop:
            self._add_down_to_stop_constraints()
        if self._DD:
            self._add_dd_gradient_auxiliary_constraints()

    def _add_turned_on_constraints(self) -> None:
        """eq. (3) — identical in all combinations."""
        m = self._m
        ts = m.parameters.temporal.timestep
        # Third constraint (>=) is named only when not _has_flat and (_has_stop or _has_start)
        named = not self._has_flat and (self._has_stop or self._has_start)
        for t in m.time_frame:
            m.add_constraint(m.turned_on.get_value(t) <= 1 - m.OFF.get_value(t))
            m.add_constraint(m.turned_on.get_value(t) <= m.OFF.get_value(t - ts))
            m.add_constraint(
                m.turned_on.get_value(t) >= m.OFF.get_value(t - ts) - m.OFF.get_value(t),
                f"constraints_defining_turned_on_{t}" if named else None,
            )

    def _add_turned_off_constraints(self) -> None:
        """eq. (4) when T_stop == 0, eq. (5) when T_stop >= 1."""
        m = self._m
        ts = m.parameters.temporal.timestep
        # Third constraint (>=) is named only when not _has_flat and (_has_stop or _has_start)
        named = not self._has_flat and (self._has_stop or self._has_start)
        for t in m.time_frame:
            if self._has_stop:
                m.add_constraint(m.turned_off.get_value(t) <= 1 - m.STOP.get_value(t - ts))
                m.add_constraint(m.turned_off.get_value(t) <= m.STOP.get_value(t))
                m.add_constraint(
                    m.turned_off.get_value(t) >= m.STOP.get_value(t) - m.STOP.get_value(t - ts),
                    f"constraints_defining_turned_off_{t}" if named else None,
                )
            else:
                m.add_constraint(m.turned_off.get_value(t) <= 1 - m.OFF.get_value(t - ts))
                m.add_constraint(m.turned_off.get_value(t) <= m.OFF.get_value(t))
                m.add_constraint(
                    m.turned_off.get_value(t) >= m.OFF.get_value(t) - m.OFF.get_value(t - ts),
                    f"constraints_defining_turned_off_{t}" if named else None,
                )

    def _add_stable_constraints(self) -> None:
        """eq. (6) — T_stable >= 1 only."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.time_frame_union_minus_one:
            m.add_constraint(m.stable.get_value(t) <= 1 - m.ON_FLAT.get_value(t - ts))
            m.add_constraint(m.stable.get_value(t) <= m.ON_FLAT.get_value(t))
            m.add_constraint(m.stable.get_value(t) >= m.ON_FLAT.get_value(t) - m.ON_FLAT.get_value(t - ts))

    def _add_entered_up_down_constraints(self) -> None:
        """eqs. (7) and (8) — T_stable >= 1 only."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.time_frame_union_minus_one:
            m.add_constraint(m.entered_up.get_value(t) <= 1 - m.ON_UP.get_value(t - ts))
            m.add_constraint(m.entered_up.get_value(t) <= m.ON_UP.get_value(t))
            m.add_constraint(m.entered_up.get_value(t) >= m.ON_UP.get_value(t) - m.ON_UP.get_value(t - ts))
            m.add_constraint(m.entered_down.get_value(t) <= 1 - m.ON_DOWN.get_value(t - ts))
            m.add_constraint(m.entered_down.get_value(t) <= m.ON_DOWN.get_value(t))
            m.add_constraint(m.entered_down.get_value(t) >= m.ON_DOWN.get_value(t) - m.ON_DOWN.get_value(t - ts))

    def _add_ud_gradient_auxiliary_constraints(self) -> None:
        """eqs. (27–30): tilde_U, tilde_D, U, D — T_stable >= 1 only."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.time_frame:
            t_prev = t - ts
            # tilde_U (eq. 28)
            m.add_constraint(m.get_variable(m.aux_up_grad_at(t)) <= m.Q_max * m.ON_UP.get_value(t_prev))
            m.add_constraint(m.get_variable(m.aux_up_grad_at(t)) >= m.Q_min * m.ON_UP.get_value(t_prev))
            m.add_constraint(
                m.get_variable(m.aux_up_grad_at(t))
                <= m.q.get_value(t) - m.q.get_value(t_prev) - m.Q_min * (1 - m.ON_UP.get_value(t_prev))
            )
            m.add_constraint(
                m.get_variable(m.aux_up_grad_at(t))
                >= m.q.get_value(t) - m.q.get_value(t_prev) - m.Q_max * (1 - m.ON_UP.get_value(t_prev)),
                f"VALUE_of_tilde_UP_at_{t}",
            )
            # tilde_D (eq. 30)
            m.add_constraint(m.get_variable(m.aux_down_grad_at(t)) <= m.Q_max * m.ON_DOWN.get_value(t_prev))
            m.add_constraint(m.get_variable(m.aux_down_grad_at(t)) >= m.Q_min * m.ON_DOWN.get_value(t_prev))
            m.add_constraint(
                m.get_variable(m.aux_down_grad_at(t))
                <= m.q.get_value(t) - m.q.get_value(t_prev) - m.Q_min * (1 - m.ON_DOWN.get_value(t_prev))
            )
            m.add_constraint(
                m.get_variable(m.aux_down_grad_at(t))
                >= m.q.get_value(t) - m.q.get_value(t_prev) - m.Q_max * (1 - m.ON_DOWN.get_value(t_prev)),
                f"VALUE_of_tilde_DOWN_at_{t}",
            )
        for t in m.time_frame:
            # U (eq. 27)
            m.add_constraint(m.U.get_value(t) <= m.Q_max * m.ON_UP.get_value(t))
            m.add_constraint(m.U.get_value(t) >= m.Q_min * m.ON_UP.get_value(t))
            m.add_constraint(
                m.U.get_value(t) <= m.get_variable(m.aux_up_grad_at(t)) - m.Q_min * (1 - m.ON_UP.get_value(t))
            )
            m.add_constraint(
                m.U.get_value(t) >= m.get_variable(m.aux_up_grad_at(t)) - m.Q_max * (1 - m.ON_UP.get_value(t)),
                f"VALUE_of_UP_at_{t}",
            )
            # D (eq. 29)
            m.add_constraint(m.D.get_value(t) <= m.Q_max * m.ON_DOWN.get_value(t))
            m.add_constraint(m.D.get_value(t) >= m.Q_min * m.ON_DOWN.get_value(t))
            m.add_constraint(
                m.D.get_value(t) <= m.get_variable(m.aux_down_grad_at(t)) - m.Q_min * (1 - m.ON_DOWN.get_value(t))
            )
            m.add_constraint(
                m.D.get_value(t) >= m.get_variable(m.aux_down_grad_at(t)) - m.Q_max * (1 - m.ON_DOWN.get_value(t)),
                f"VALUE_of_DOWN_at_{t}",
            )

    def _add_down_to_stop_constraints(self) -> None:
        """eq. (20) — T_stop >= 1 and T_stable == 0 only."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.time_frame:
            t_prev = t - ts
            m.add_constraint(self._down_to_stop[t] <= m.STOP.get_value(t))
            m.add_constraint(self._down_to_stop[t] <= m.ON_DOWN.get_value(t_prev))
            m.add_constraint(self._down_to_stop[t] >= m.STOP.get_value(t) + m.ON_DOWN.get_value(t_prev) - 1)

    def _add_flat_down_stop_constraints(self) -> None:
        """eq. (22) — T_stop >= 1 and T_stable >= 1 only."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.time_frame:
            t_prev = t - ts
            t_prev2 = t - 2 * ts
            m.add_constraint(self._flat_down_stop[t] <= m.STOP.get_value(t))
            m.add_constraint(self._flat_down_stop[t] <= m.ON_DOWN.get_value(t_prev))
            m.add_constraint(self._flat_down_stop[t] <= m.ON_FLAT.get_value(t_prev2))
            m.add_constraint(
                self._flat_down_stop[t]
                >= m.STOP.get_value(t) + m.ON_DOWN.get_value(t_prev) + m.ON_FLAT.get_value(t_prev2) - 2
            )

    def _add_dd_gradient_auxiliary_constraints(self) -> None:
        """eq. (23) — T_stop >= 1 and T_stable >= 1 only."""
        m = self._m
        ts = m.parameters.temporal.timestep
        for t in m.gradients_time_frame:
            t_next = t + ts
            m.add_constraint(self._DD[t] <= m.Q_max * m.STOP.get_value(t_next))
            m.add_constraint(self._DD[t] >= m.Q_min * m.STOP.get_value(t_next))
            m.add_constraint(self._DD[t] <= m.D.get_value(t) - m.Q_min * (1 - m.STOP.get_value(t_next)))
            m.add_constraint(
                self._DD[t] >= m.D.get_value(t) - m.Q_max * (1 - m.STOP.get_value(t_next)),
                f"DD_gradient_auxiliary_at_{t}",
            )

    # ──────────────────────────────────────────────────────────────────────
    # State variable constraints (Section C in original files)
    # ──────────────────────────────────────────────────────────────────────

    def _add_state_variable_constraints(self) -> None:
        self._add_mutual_exclusion()
        self._add_transition_constraints()
        if self._has_start or self._has_stop:
            self._add_eviction_constraints()
        self._add_minimum_time_constraints()

    def _add_mutual_exclusion(self) -> None:
        """eq. (9) — all active state variables must sum to 1."""
        m = self._m
        # When T_stable >= 1, ON_FLAT is defined over time_frame_union_minus_one
        tf = m.time_frame_union_minus_one if self._has_flat else m.time_frame
        for t in tf:
            expr = m.OFF.get_value(t) + m.ON_UP.get_value(t) + m.ON_DOWN.get_value(t)
            if self._has_flat:
                expr = expr + m.ON_FLAT.get_value(t)
            if self._has_stop:
                expr = expr + m.STOP.get_value(t)
            if self._has_start:
                expr = expr + m.START.get_value(t)
            name = (
                None
                if (not self._has_flat and not self._has_start and not self._has_stop)
                else f"mutual_exclusion_at_{t}"
            )
            m.add_constraint(expr == 1, name)

    def _add_transition_constraints(self) -> None:
        """Add all forbidden state transition constraints."""
        m = self._m
        ts = m.parameters.temporal.timestep

        if not self._has_flat and not self._has_start and not self._has_stop:
            return  # Combination 1: all transitions allowed

        if self._has_flat:
            for t in m.time_frame_union_minus_one:
                t_prev = t - ts
                # UP ↔ DOWN forbidden (eq. 25)
                m.add_constraint(m.ON_UP.get_value(t_prev) + m.ON_DOWN.get_value(t) <= 1)
                # Named only for comb 3 (flat, no_stop, no_start)
                down_up_name = (
                    f"transitions_constraints_at_{t}" if (not self._has_stop and not self._has_start) else None
                )
                m.add_constraint(m.ON_DOWN.get_value(t_prev) + m.ON_UP.get_value(t) <= 1, down_up_name)
                if self._has_stop:
                    # STOP → ON forbidden (eq. 13)
                    m.add_constraint(m.STOP.get_value(t_prev) + m.ON_FLAT.get_value(t) <= 1)
                    m.add_constraint(m.STOP.get_value(t_prev) + m.ON_DOWN.get_value(t) <= 1)
                    m.add_constraint(
                        m.STOP.get_value(t_prev) + m.ON_UP.get_value(t) <= 1,
                        f"transitions_constraints_on_timeFrame_union_minus_one_at_{t}",
                    )

            for t in m.time_frame:
                t_prev = t - ts
                if self._has_stop:
                    m.add_constraint(m.ON_UP.get_value(t_prev) + m.STOP.get_value(t) <= 1)  # eq. (21)
                    # OFF→STOP: named only when no _has_start (comb 5); unnamed for comb 8
                    off_stop_name = f"transitions_constraints_at_{t}" if not self._has_start else None
                    m.add_constraint(m.OFF.get_value(t_prev) + m.STOP.get_value(t) <= 1, off_stop_name)  # eq. (12)
                if self._has_start:
                    m.add_constraint(m.ON_UP.get_value(t_prev) + m.START.get_value(t) <= 1)  # eq. (10)
                    m.add_constraint(m.ON_DOWN.get_value(t_prev) + m.START.get_value(t) <= 1)  # eq. (10)
                    m.add_constraint(m.ON_FLAT.get_value(t_prev) + m.START.get_value(t) <= 1)  # eq. (10)
                    m.add_constraint(m.START.get_value(t_prev) + m.OFF.get_value(t) <= 1)  # eq. (11)
                    if self._has_stop:
                        m.add_constraint(m.START.get_value(t_prev) + m.STOP.get_value(t) <= 1)  # eq. (14)
                        m.add_constraint(m.STOP.get_value(t_prev) + m.START.get_value(t) <= 1)  # eq. (14)
                    # OFF → ON forbidden (eq. 15) — only when has_start
                    m.add_constraint(m.OFF.get_value(t_prev) + m.ON_UP.get_value(t) <= 1)
                    if self._has_stop:
                        # Comb 8: OFF→ON_FLAT, OFF→ON_DOWN (named last)
                        m.add_constraint(m.OFF.get_value(t_prev) + m.ON_FLAT.get_value(t) <= 1)
                        m.add_constraint(
                            m.OFF.get_value(t_prev) + m.ON_DOWN.get_value(t) <= 1,
                            f"transitions_constraints_at_{t}",
                        )
                    else:
                        # Comb 6: OFF→ON_DOWN, OFF→ON_FLAT (named last)
                        m.add_constraint(m.OFF.get_value(t_prev) + m.ON_DOWN.get_value(t) <= 1)
                        m.add_constraint(
                            m.OFF.get_value(t_prev) + m.ON_FLAT.get_value(t) <= 1,
                            f"transitions_constraints_at_{t}",
                        )
        else:
            # No ON_FLAT — simpler transition set (combinations 2, 4, 7)
            for t in m.time_frame:
                t_prev = t - ts
                if self._has_stop:
                    m.add_constraint(m.STOP.get_value(t_prev) + m.ON_UP.get_value(t) <= 1)  # eq. (13)
                    m.add_constraint(m.STOP.get_value(t_prev) + m.ON_DOWN.get_value(t) <= 1)  # eq. (13)
                    m.add_constraint(m.OFF.get_value(t_prev) + m.STOP.get_value(t) <= 1)  # eq. (12)
                    m.add_constraint(m.ON_UP.get_value(t_prev) + m.OFF.get_value(t) <= 1)  # eq. (18)
                    if not self._has_start:
                        # Comb 2: ON_DOWN→OFF is last and named
                        m.add_constraint(
                            m.ON_DOWN.get_value(t_prev) + m.OFF.get_value(t) <= 1,
                            f"transitions_constraints_at_{t}",
                        )  # eq. (18)
                    else:
                        m.add_constraint(m.ON_DOWN.get_value(t_prev) + m.OFF.get_value(t) <= 1)  # eq. (18)
                if self._has_start:
                    m.add_constraint(m.ON_UP.get_value(t_prev) + m.START.get_value(t) <= 1)  # eq. (10)
                    m.add_constraint(m.ON_DOWN.get_value(t_prev) + m.START.get_value(t) <= 1)  # eq. (10)
                    m.add_constraint(m.START.get_value(t_prev) + m.OFF.get_value(t) <= 1)  # eq. (11)
                    if self._has_stop:
                        # Comb 7: START→STOP, STOP→START before OFF→ON
                        m.add_constraint(m.START.get_value(t_prev) + m.STOP.get_value(t) <= 1)  # eq. (14)
                        m.add_constraint(m.STOP.get_value(t_prev) + m.START.get_value(t) <= 1)  # eq. (14)
                    m.add_constraint(m.OFF.get_value(t_prev) + m.ON_UP.get_value(t) <= 1)  # eq. (15)
                    m.add_constraint(
                        m.OFF.get_value(t_prev) + m.ON_DOWN.get_value(t) <= 1,
                        f"transitions_constraints_at_{t}",
                    )  # eq. (15)

    def _add_eviction_constraints(self) -> None:
        """Force unit to leave START/STOP after their respective durations."""
        m = self._m
        ts = m.parameters.temporal.timestep
        both = self._has_start and self._has_stop
        for t in m.time_frame:
            if both and not self._has_flat:
                # Comb 7: START eviction first, STOP eviction second
                m.add_constraint(
                    m.turned_on.get_value(t - m.T_start * ts) + m.START.get_value(t) <= 1,
                    f"START_eviction_constraint_at_{t}",
                )
                m.add_constraint(
                    m.turned_off.get_value(t - m.T_stop * ts) + m.STOP.get_value(t) <= 1,
                    f"STOP_eviction_constraint_at_{t}",
                )
            elif both and self._has_flat:
                # Comb 8: STOP eviction first, START eviction second
                m.add_constraint(
                    m.turned_off.get_value(t - m.T_stop * ts) + m.STOP.get_value(t) <= 1,
                    f"STOP_eviction_constraint_at_{t}",
                )
                m.add_constraint(
                    m.turned_on.get_value(t - m.T_start * ts) + m.START.get_value(t) <= 1,
                    f"START_eviction_constraint_at_{t}",
                )
            else:
                # Single eviction type — plain name (combs 2, 4, 5, 6)
                if self._has_start:
                    m.add_constraint(
                        m.turned_on.get_value(t - m.T_start * ts) + m.START.get_value(t) <= 1,
                        f"eviction_constraint_at_{t}",
                    )
                if self._has_stop:
                    m.add_constraint(
                        m.turned_off.get_value(t - m.T_stop * ts) + m.STOP.get_value(t) <= 1,
                        f"eviction_constraint_at_{t}",
                    )

    def _add_minimum_time_constraints(self) -> None:
        """Minimum time in ON, OFF, FLAT, START, STOP states."""
        m = self._m
        ts = m.parameters.temporal.timestep
        tf_flat = m.time_frame_union_minus_one if self._has_flat else m.time_frame

        if m.T_on >= 2:
            for t in tf_flat:
                on_expr = m.ON_UP.get_value(t) + m.ON_DOWN.get_value(t)
                if self._has_flat:
                    on_expr = on_expr + m.ON_FLAT.get_value(t)
                for s in range(1, m.T_on):
                    t_ref = t - s * ts
                    if self._has_start:
                        t_ref = t_ref - m.T_start * ts
                    m.add_constraint(
                        m.turned_on.get_value(t_ref) <= on_expr,
                        f"minimum_time_ON_{m.thermal_unit.name}_at_{t_ref}_for_{t}",
                    )

        if m.T_off >= 2:
            for t in m.time_frame:
                for s in range(1, m.T_off):
                    t_ref = t - s * ts
                    if self._has_stop:
                        t_ref = t_ref - m.T_stop * ts
                    m.add_constraint(
                        m.turned_off.get_value(t_ref) <= m.OFF.get_value(t),
                        f"minimum_time_OFF_{m.thermal_unit.name}_at_{t_ref}_for_{t}",
                    )

        if m.T_stable >= 2:
            for t in m.time_frame_union_minus_one:
                for s in range(1, m.T_stable - 1):
                    t_ref = t - s * ts
                    m.add_constraint(
                        m.stable.get_value(t_ref) <= m.ON_FLAT.get_value(t),
                        f"minimum_time_STABLE_{m.thermal_unit.name}_at_{t_ref}_for_{t}",
                    )

        if m.T_stop >= 2:
            for t in m.time_frame:
                for s in m.stop_time_steps:
                    t_ref = t - s * ts
                    m.add_constraint(
                        m.turned_off.get_value(t_ref) <= m.STOP.get_value(t),
                        f"shutdown_ramp_of_{m.thermal_unit.name}_at_{t_ref}_for_{t}",
                    )

        if m.T_start >= 2:
            # Combination 4 (has_start, no_stop, no_flat) uses "startup_ramp_of_" (no space)
            ramp_prefix = (
                "startup_ramp_of_"
                if (self._has_start and not self._has_stop and not self._has_flat)
                else "start_up_ramp_of_"
            )
            for t in m.time_frame:
                for s in m.start_time_steps:
                    t_ref = t - s * ts
                    m.add_constraint(
                        m.turned_on.get_value(t_ref) <= m.START.get_value(t),
                        f"{ramp_prefix}{m.thermal_unit.name}_at_{t_ref}_for_{t}",
                    )

    # ──────────────────────────────────────────────────────────────────────
    # Control variable constraints (Section D in original files)
    # ──────────────────────────────────────────────────────────────────────

    def _add_control_variable_constraints(self) -> None:
        self._add_contracted_diff_constraints()
        self._add_fill_up_constraints()
        self._add_relaxed_reserve_constraint()
        self._add_reserve_capacity_constraints()
        self._add_power_bounds()
        self._add_gradient_constraints()

    def _add_contracted_diff_constraints(self) -> None:
        """eqs. (39) and (40) — contracted difference for manual and automated reserves."""
        m = self._m
        for t in m.time_frame:
            m.add_constraint(
                m.get_variable(m.contracted_difference_up_at(t))
                >= m.reserves_up_procured.get_value(t) - m.get_variable(m.reserves_up_equip_at(t))
            )
            m.add_constraint(
                m.get_variable(m.contracted_difference_down_at(t))
                >= m.reserves_down_procured.get_value(t) - m.get_variable(m.reserves_down_equip_at(t))
            )
            m.add_constraint(
                m.get_variable(m.automated_contracted_difference_up_at(t))
                >= m.feasible_automated_reserves_up_procured.get_value(t)
                - m.get_variable(m.automated_reserves_up_at(t))
            )
            m.add_constraint(
                m.get_variable(m.automated_contracted_difference_down_at(t))
                >= m.feasible_automated_reserves_down_procured.get_value(t)
                - m.get_variable(m.automated_reserves_down_at(t))
            )

    def _add_fill_up_constraints(self) -> None:
        """eqs. (41) and (42) — upward and downward fill-up constraints."""
        m = self._m
        eps = m.parameters.epsilon
        for t in m.time_frame:
            up_sum = (
                m.q.get_value(t)
                + m.get_variable(m.reserves_up_equip_at(t))
                + m.get_variable(m.automated_reserves_up_at(t))
                + m.get_variable(m.unprovided_reserves_up_at(t))
            )
            m.add_constraint(up_sum <= m.q_upper.get_value(t) + eps)
            m.add_constraint(up_sum >= m.q_upper.get_value(t) - eps)

            down_sum = (
                m.q.get_value(t)
                - m.get_variable(m.reserves_down_equip_at(t))
                - m.get_variable(m.automated_reserves_down_at(t))
                - m.get_variable(m.unprovided_reserves_down_at(t))
                + m.get_variable(m.relaxed_reserves_at(t))
            )
            m.add_constraint(down_sum <= m.q_lower.get_value(t) + eps)
            m.add_constraint(down_sum >= m.q_lower.get_value(t) - eps)

    def _add_relaxed_reserve_constraint(self) -> None:
        """eq. (43)."""
        m = self._m
        for t in m.time_frame:
            online_sum = m.ON_UP.get_value(t) + m.ON_DOWN.get_value(t)
            if self._has_flat:
                online_sum = online_sum + m.ON_FLAT.get_value(t)
            m.add_constraint(m.get_variable(m.relaxed_reserves_at(t)) <= m.q_lower.get_value(t) * (1 - online_sum))

    def _add_reserve_capacity_constraints(self) -> None:
        """eqs. (44) and (45)."""
        m = self._m
        for t in m.time_frame:
            # Automated reserves unavailable in OFF and ramp states
            unavailable = m.OFF.get_value(t)
            if self._has_start:
                unavailable = unavailable + m.START.get_value(t)
            if self._has_stop:
                unavailable = unavailable + m.STOP.get_value(t)

            m.add_constraint(m.get_variable(m.automated_reserves_up_at(t)) <= m.maximum_automated * (1 - unavailable))
            m.add_constraint(m.get_variable(m.automated_reserves_down_at(t)) <= m.maximum_automated * (1 - unavailable))

            # Equipment reserves also unavailable in ON_UP/ON_DOWN when FLAT state exists (eq. 45)
            res_unavailable = unavailable
            if self._has_flat:
                res_unavailable = res_unavailable + m.ON_UP.get_value(t) + m.ON_DOWN.get_value(t)

            m.add_constraint(
                m.get_variable(m.reserves_up_equip_at(t)) <= m.q_upper.get_value(t) * (1 - res_unavailable)
            )
            m.add_constraint(
                m.get_variable(m.reserves_down_equip_at(t)) <= m.q_upper.get_value(t) * (1 - res_unavailable)
            )

    def _add_power_bounds(self) -> None:
        """eqs. (33) and (34) — lower and upper bounds on q."""
        m = self._m
        q_min = m.thermal_unit.minimum_power.max()
        q_step_down = q_min / m.T_stop if self._has_stop else 0

        for t in m.time_frame:
            online_sum = m.ON_UP.get_value(t) + m.ON_DOWN.get_value(t)
            if self._has_flat:
                online_sum = online_sum + m.ON_FLAT.get_value(t)

            lb = m.q_lower.get_value(t) * online_sum
            if self._has_stop:
                lb = lb + m.turned_off.get_value(t) * (q_min - q_step_down)
            m.add_constraint(m.q.get_value(t) >= lb, f"lower_bound_of_{m.thermal_unit.name}_at_{t}")

            ub = m.q_upper.get_value(t) * online_sum
            if self._has_stop:
                ub = ub + m.STOP.get_value(t) * q_min - m.turned_off.get_value(t) * q_step_down
            if self._has_start:
                ub = ub + m.START.get_value(t) * q_min
            m.add_constraint(m.q.get_value(t) <= ub, f"upper_bound_of_{m.thermal_unit.name}_at_{t}")

    def _add_daily_energy_constraint(self) -> None:
        """Limit total energy output per calendar day when the unit has a daily energy cap."""
        m = self._m
        if not m.thermal_unit.has_daily_energy_constraint:
            return
        days = sorted({datetime(t.year, t.month, t.day) for t in m.time_frame})
        for day in days:
            steps = [t for t in m.time_frame if t.year == day.year and t.month == day.month and t.day == day.day]
            if steps and m.thermal_unit.maximum_daily_energy is not None:
                m.add_constraint(
                    sum(m.q.get_value(t) for t in steps)
                    <= m.thermal_unit.maximum_daily_energy.get_value(day)
                    * m.parameters.temporal.timestep.total_days()
                    * len(steps),
                    f"energy_limit_of_{m.thermal_unit.name}_at_{day}",
                )

    def _add_gradient_constraints(self) -> None:
        """eqs. (35–38) — upward and downward power gradient constraints."""
        m = self._m
        ts = m.parameters.temporal.timestep

        if m.delta_q < 0:
            cfg.logger.error(
                f"No gradients have been defined for equipment {m.thermal_unit.name}. \n "
                "Please check the value of `maximum_gradient`."
            )
            raise ValueError("Missing gradients for thermic units.")

        # When delta_q == 0, the gradient is effectively unconstrained between timesteps
        dq = m.delta_q if m.delta_q > 0 else m.delta_q_unconstrained
        q_min = m.thermal_unit.minimum_power.max()
        q_step_up = q_min / m.T_start if self._has_start else 0
        q_step_down = q_min / m.T_stop if self._has_stop else 0

        for t in m.gradients_time_frame:
            t_next = t + ts

            # --- Upward gradient base ---
            if self._has_flat:
                up = dq * m.entered_up.get_value(t) + m.U.get_value(t) + m.D.get_value(t)
            else:
                up = dq * m.ON_UP.get_value(t)

            # --- Downward gradient base ---
            if self._has_flat:
                down = -dq * m.entered_down.get_value(t) + m.U.get_value(t) + m.D.get_value(t)
            else:
                down = -dq * m.ON_DOWN.get_value(t)

            # Startup contribution
            if self._has_start:
                startup = q_step_up * m.turned_on.get_value(t_next) + m.START.get_value(t) * q_step_up
                up = up + startup
                down = down + startup
            else:
                # Free (unconstrained) startup — only in the upward direction
                up = up + m.delta_q_unconstrained * m.turned_on.get_value(t_next)

            # Shutdown contribution
            if self._has_stop:
                shutdown = -m.turned_off.get_value(t_next) * q_step_down - m.STOP.get_value(t) * q_step_down
                up = up + shutdown
                down = down + shutdown
                # Path correction for the downward gradient near shutdown
                if self._flat_down_stop:
                    down = down + self._flat_down_stop[t_next] * dq  # eq. (22) contribution
                else:
                    down = down + self._down_to_stop[t_next] * dq  # eq. (20) contribution
                # DD correction (eq. 23) — activated when gradient locked into STOP
                if self._DD:
                    up = up - self._DD[t]
                    down = down - self._DD[t]
            else:
                # Free (unconstrained) shutdown — only in the downward direction
                down = down - m.delta_q_unconstrained * m.turned_off.get_value(t_next)

            m.add_constraint(
                m.q.get_value(t_next) - m.q.get_value(t) <= up,
                f"upward_gradient_of_{m.thermal_unit.name}_at_{t}",
            )
            m.add_constraint(
                m.q.get_value(t_next) - m.q.get_value(t) >= down,
                f"downward_gradient_of_{m.thermal_unit.name}_at_{t}",
            )
