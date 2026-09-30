"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from pendulum import DateTime, Duration

from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.enums import VariableType
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from collections.abc import Iterable

    from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput
    from atlas.solver.temporal_variable import TemporalVariable


class ThermalDispatch:
    """
    Physical dispatch model for a single thermal unit.

    Owns the model variables and the physical constraints. Reserves, fill-up constraints
    and objective terms stay in the calling module.

    **The state machine.** At every timestep the unit occupies exactly one state — see
    :meth:`_add_mutual_exclusion`::

        OFF ──▶ START ──▶ ON_UP ⇄ ON_FLAT ⇄ ON_DOWN ──▶ STOP ──▶ OFF
                 ramp    └──── power free to move ────┘    ramp

    ``START`` and ``STOP`` are the startup and shutdown ramps, ``ON_FLAT`` the stable
    plateau. All three are optional, so a unit only carries the states its characteristics
    give it — :meth:`_add_transition_constraints` bans whatever the resulting machine
    cannot do:

    - startup ramp — :attr:`has_start`, exists when ``T_start >= 1``, state ``on_start``
    - shutdown ramp — :attr:`has_stop`, exists when ``T_stop >= 1``, state ``stop``
    - stable plateau — :attr:`has_flat`, exists when ``T_stable >= 1``, state ``on_flat``

    The eight ways of combining those three flags are the eight model variants the codebase
    calls *combinations 1 to 8* (:attr:`combination`), one per ``thermal-combination-*``
    test dataset.

    **The two regimes.** The model reaches back before the delivery window. Ahead of
    ``temporal.start_date`` the unit's state is *known*: it is derived from the initial
    conditions and fixed on the temporal variables. Inside the window it is a decision
    variable. Reading ``variable[t]`` hides the difference, so a constraint reaching across
    the boundary silently mixes constants and variables.

    The past is fixed by :meth:`_add_initial_conditions`: classify each past step from its
    power, then derive the markers as rising edges of those states. One exception: ON_UP,
    ON_DOWN and ON_FLAT describe the move to the next step, so on the step before the
    window they depend on the window and stay solver variables. With a plateau that step is
    therefore part of the model: :meth:`_add_step_before_window` emits its rows. A row
    anchored before ``start_date`` degenerates instead of binding, and mutual exclusion
    does not apply between constants.

    Typical usage::

        dispatch = ThermalDispatch(equipment)
        dispatch.setup(model, parameters)                 # declare vars + fix initial conditions
        dispatch.add_variables(time_window)               # decision variables over the window
        for time in time_window:
            dispatch.add_constraints(model, time, parameters)
    """

    #: Model variant per ``(has_stop, has_start, has_flat)``. The number carries no meaning
    #: of its own — it labels the combination in logs and names the test datasets.
    _COMBINATIONS: ClassVar[dict[tuple[bool, bool, bool], int]] = {
        (False, False, False): 1,
        (True, False, False): 2,
        (False, False, True): 3,
        (False, True, False): 4,
        (True, False, True): 5,
        (False, True, True): 6,
        (True, True, False): 7,
        (True, True, True): 8,
    }

    #: State changes the machine forbids, per ``(has_stop, has_start, has_flat)``. Each
    #: ``(from, to)`` pair becomes ``from(t-1) + to(t) <= 1``.
    #:
    #: Two rules generate it: a ramp cannot be skipped (STOP is the only way to OFF, START
    #: the only way in), and the power cannot reverse in one step once a plateau exists to
    #: sit between ON_UP and ON_DOWN.
    #:
    #: A ban's number is its position, so **the order is part of the LP names** — append,
    #: never insert.
    _BANNED_TRANSITIONS: ClassVar[dict[tuple[bool, bool, bool], tuple[tuple[str, str], ...]]] = {
        # 1 — no ramp, no plateau: the unit is free, nothing to forbid
        (False, False, False): (),
        # 2 — shutdown ramp only: OFF is reachable through STOP alone
        (True, False, False): (
            ("stop", "on_up"),
            ("stop", "on_down"),
            ("off", "stop"),
            ("on_up", "off"),
            ("on_down", "off"),
        ),
        # 3 — plateau only: the power just cannot reverse without passing through it
        (False, False, True): (
            ("on_up", "on_down"),
            ("on_down", "on_up"),
        ),
        # 4 — startup ramp only: ON is reachable through START alone
        (False, True, False): (
            ("on_up", "on_start"),
            ("on_down", "on_start"),
            ("on_start", "off"),
            ("off", "on_up"),
            ("off", "on_down"),
        ),
        # 5 — shutdown ramp + plateau
        (True, False, True): (
            ("on_up", "on_down"),
            ("on_down", "on_up"),
            ("on_up", "off"),
            ("on_down", "off"),
            ("stop", "on_flat"),
            ("stop", "on_down"),
            ("stop", "on_up"),
            ("on_up", "stop"),
            ("off", "stop"),
        ),
        # 6 — startup ramp + plateau
        (False, True, True): (
            ("on_up", "on_down"),
            ("on_down", "on_up"),
            ("on_up", "on_start"),
            ("on_down", "on_start"),
            ("on_flat", "on_start"),
            ("on_start", "off"),
            ("off", "on_flat"),
            ("off", "on_down"),
            ("off", "on_up"),
        ),
        # 7 — both ramps, no plateau
        (True, True, False): (
            ("stop", "on_up"),
            ("stop", "on_down"),
            ("off", "stop"),
            ("on_up", "off"),
            ("on_down", "off"),
            ("on_up", "on_start"),
            ("on_down", "on_start"),
            ("on_start", "off"),
            ("on_start", "stop"),
            ("stop", "on_start"),
            ("off", "on_up"),
            ("off", "on_down"),
        ),
        # 8 — both ramps + plateau: every state exists, so every illegal pair is listed
        (True, True, True): (
            ("on_up", "on_down"),
            ("on_down", "on_up"),
            ("stop", "on_flat"),
            ("stop", "on_down"),
            ("stop", "on_up"),
            ("on_up", "stop"),
            ("off", "stop"),
            ("on_up", "on_start"),
            ("on_down", "on_start"),
            ("on_flat", "on_start"),
            ("on_up", "off"),
            ("on_down", "off"),
            ("on_flat", "off"),
            ("on_start", "off"),
            ("on_start", "stop"),
            ("stop", "on_start"),
            ("off", "on_up"),
            ("off", "on_flat"),
            ("off", "on_down"),
        ),
    }

    #: Bans re-emitted on the step before the window: the power reversals and the bans out of
    #: STOP, the ones reaching a direction state still left to the solver there.
    _BOUNDARY_BANS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("on_up", "on_down"),
        ("on_down", "on_up"),
        ("stop", "on_flat"),
        ("stop", "on_down"),
        ("stop", "on_up"),
    )

    def __init__(self, equipment: ThermalDispatchInput) -> None:
        self._eq = equipment

        # Time parameters — populated by setup()
        self._T_on: int = 0
        self._T_off: int = 0
        self._T_start: int = 0
        self._T_stop: int = 0
        self._T_stable: int = 0
        self._Delta_Q: float = 0.0
        self._maximum_power_swing: float = 0.0
        self._combination: int = 1

        # Booleans derived from T params — set after _compute_time_parameters
        self._has_stop: bool = False
        self._has_start: bool = False
        self._has_flat: bool = False

        # Temporal variables — declared by _declare_variables(), grouped by role

        # States — exactly one of these is 1 at any timestep
        self.off: TemporalVariable
        self.on_start: TemporalVariable
        self.on_up: TemporalVariable
        self.on_flat: TemporalVariable
        self.on_down: TemporalVariable
        self.stop: TemporalVariable

        # Transition markers — fire on the step the unit enters the matching state
        self.turned_on: TemporalVariable
        self.turned_off: TemporalVariable
        self.entered_up: TemporalVariable
        self.entered_down: TemporalVariable
        self.stable: TemporalVariable
        self.flat_down_stop: TemporalVariable
        self.down_to_stop_grad: TemporalVariable

        # Gradient auxiliaries — linearised products of a power step by a state
        self.up_grad: TemporalVariable
        self.down_grad: TemporalVariable
        self.aux_up_grad: TemporalVariable
        self.aux_down_grad: TemporalVariable
        self.dd_grad: TemporalVariable

        # The dispatch
        self.power_level: TemporalVariable

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def T_start(self) -> int:
        """Number of startup-ramp timesteps (``floor(startup_duration / timestep)``)."""
        return self._T_start

    @property
    def T_stop(self) -> int:
        """Number of shutdown-ramp timesteps (``floor(shutdown_duration / timestep)``)."""
        return self._T_stop

    @property
    def has_start(self) -> bool:
        """True if the unit has a startup ramp phase (T_start >= 1)."""
        return self._has_start

    @property
    def has_stop(self) -> bool:
        """True if the unit has a shutdown ramp phase (T_stop >= 1)."""
        return self._has_stop

    @property
    def has_flat(self) -> bool:
        """True if the unit has a flat stable phase (T_stable >= 1)."""
        return self._has_flat

    def setup(self, model: OptimisationModel, parameters: AbstractModuleParameters) -> None:
        """
        Compute time parameters, declare the temporal variables, and fix initial conditions.

        Must be called before :meth:`add_variables` or :meth:`add_constraints`.

        :param model: The optimisation model
        :param parameters: Module parameters — must expose ``temporal.timestep``,
            ``temporal.start_date``, ``temporal.end_date``, ``temporal.execution_date``
        """
        self._compute_time_parameters(parameters)
        self._declare_variables(model)
        self._add_initial_variables(parameters)
        self._add_initial_conditions(parameters)

    def add_variables(self, times: Iterable[DateTime]) -> None:
        """
        Register decision variables for *times* in the model.

        Only the variables used by the unit's combination are created.

        :param times: The timesteps for which to create variables
        :type times: Iterable[DateTime]
        """
        times = list(times)
        for variable in self._window_variables():
            variable.add_all(times)

    def add_constraints(self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters) -> None:
        """
        Add all physical constraints for *time*.

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param parameters: Module parameters
        """
        ts = parameters.temporal.timestep
        prev_time = time - ts

        self._add_turned_on(model, time, prev_time)
        self._add_turned_off(model, time, prev_time)

        if self._has_flat:
            self._add_stable(model, time, prev_time)
            if self._has_stop:
                self._add_flat_down_stop(model, time, prev_time, ts)
            self._add_entered_up_down(model, time, prev_time)
            self._add_gradient_auxiliaries(model, time, prev_time)

        if self._has_stop and not self._has_flat:
            self._add_down_to_stop_evol(model, time, prev_time)

        self._add_mutual_exclusion(model, time)

        if self._has_flat and time == parameters.temporal.start_date:
            self._add_step_before_window(model, prev_time, ts)

        self._add_transition_constraints(model, time, prev_time)
        self._add_eviction_constraints(model, time, parameters)
        self._add_minimum_time_constraints(model, time, parameters)
        self._add_power_bounds(model, time)

    def add_daily_energy_constraint(
        self, model: OptimisationModel, time_window: list[DateTime], timestep: Duration
    ) -> None:
        """
        Add the daily energy cap constraint for each day spanned by *time_window*.

        No-op when :attr:`ThermalDispatchInput.has_daily_energy_constraint` is ``False``
        or :attr:`ThermalDispatchInput.maximum_daily_energy` is ``None``.

        :param model: The optimisation model
        :param time_window: Ordered list of timesteps to consider
        :type time_window: list[DateTime]
        :param timestep: Duration of one timestep
        :type timestep: Duration
        """
        if not self._eq.has_daily_energy_constraint or self._eq.maximum_daily_energy is None:
            return
        steps_by_day: dict[datetime, list] = {}
        for t in time_window:
            steps_by_day.setdefault(datetime(t.year, t.month, t.day), []).append(t)
        n = self._eq.name
        for day, steps in steps_by_day.items():
            model.add_constraint(
                sum(self.power_level[t] for t in steps)
                <= self._eq.maximum_daily_energy.get_value(day) * timestep.total_days() * len(steps),
                f"energy_limit_of_{n}_at_{day}",
            )

    def add_dd_and_gradient_constraints(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        """
        Add DD auxiliary and gradient constraints for *time*.

        Must only be called when *time* is not among the last two steps of the window.

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param prev_time: Previous timestep
        :type prev_time: DateTime
        """
        if self._has_flat and self._has_stop:
            self._add_dd_constraints(model, time, prev_time)
        self._add_gradient_constraints(model, time, prev_time)

    # ── Public accessors (combination / flags) ────────────────────────────

    @property
    def combination(self) -> int:
        """
        Which of the eight model variants this unit falls into — see :attr:`_COMBINATIONS`.

        Reported in logs and used to name the reference LP files; nothing in the model
        branches on the number itself, only on :attr:`has_start`, :attr:`has_stop` and
        :attr:`has_flat`.
        """
        return self._combination

    @property
    def name(self) -> str:
        """Name of the unit being dispatched."""
        return self._eq.name

    # ── Initialisation ────────────────────────────────────────────────────

    def _compute_time_parameters(self, parameters: AbstractModuleParameters) -> None:
        eq = self._eq
        temporal = parameters.temporal
        ts = temporal.timestep

        self._T_on = (
            int(max(1, math.ceil(eq.minimum_time_on / ts))) + 1
            if eq.minimum_time_on and eq.minimum_time_on.total_minutes() > 0
            else 0
        )
        self._T_off = (
            int(max(1, math.ceil(eq.minimum_time_off / ts))) + 1
            if eq.minimum_time_off and eq.minimum_time_off.total_minutes() > 0
            else 0
        )
        self._T_start = int(math.floor(eq.startup_duration / ts)) if eq.startup_duration else 0
        self._T_stop = int(math.floor(eq.shutdown_duration / ts)) if eq.shutdown_duration else 0

        if eq.minimum_stable_power_duration:
            if eq.minimum_stable_power_duration < ts:
                self._T_stable = 0
            else:
                t = int(math.ceil(eq.minimum_stable_power_duration / ts)) + 1
                self._T_stable = t if t >= 2 else 0
        else:
            self._T_stable = 0

        # 0 (or None) means the unit has no gradient limit — see Equipment.maximum_gradient
        self._Delta_Q = (eq.maximum_gradient or 0.0) * ts.total_minutes()
        # Widest power swing the unit can make. It bounds the gradient auxiliaries and the
        # products they linearise, and stands in as the free ramp of a unit with no
        # gradient limit. Taken over the whole series rather than the delivery window, so
        # that it covers every swing the model can express — including the lookahead hours
        # a module adds past end_date.
        self._maximum_power_swing = eq.maximum_power.max()

        self._has_stop = self._T_stop >= 1
        self._has_start = self._T_start >= 1
        self._has_flat = self._T_stable >= 1
        self._combination = self._COMBINATIONS[self._has_stop, self._has_start, self._has_flat]

    def _declare_variables(self, model: OptimisationModel) -> None:
        eq = self._eq
        n = eq.name

        def boolean(name: str) -> TemporalVariable:
            return model.add_temporal_variable(name, variable_type=VariableType.BOOLEAN)

        def gradient(name: str) -> TemporalVariable:
            swing = self._maximum_power_swing
            return model.add_temporal_variable(name, lower_bound=-swing, upper_bound=swing)

        # States
        self.off = boolean(f"off_{n}")
        self.on_start = boolean(f"on_start_{n}")
        self.on_up = boolean(f"on_up_{n}")
        self.on_flat = boolean(f"on_flat_{n}")
        self.on_down = boolean(f"on_down_{n}")
        self.stop = boolean(f"stop_{n}")

        # Transition markers
        self.turned_on = boolean(f"t_on_{n}")
        self.turned_off = boolean(f"t_off_{n}")
        self.entered_up = boolean(f"entered_up_{n}")
        self.entered_down = boolean(f"entered_down_{n}")
        self.stable = boolean(f"stable_{n}")
        self.flat_down_stop = boolean(f"flat_down_stop_{n}")
        self.down_to_stop_grad = boolean(f"down_to_stop_grad_{n}")

        # Gradient auxiliaries
        self.up_grad = gradient(f"up_grad_{n}")
        self.down_grad = gradient(f"down_grad_{n}")
        self.aux_up_grad = gradient(f"aux_up_grad_{n}")
        self.aux_down_grad = gradient(f"aux_down_grad_{n}")
        self.dd_grad = gradient(f"dd_grad_{n}")

        # The dispatch
        self.power_level = model.add_temporal_variable(f"{n}_power_level", lower_bound=0, upper_bound=eq.maximum_power)

    def _window_variables(self) -> list[TemporalVariable]:
        """Return the temporal variables the unit's combination needs at each timestep of the window."""
        # Always present: the unit is either off or moving, and either edge can fire
        variables = [self.off, self.on_up, self.on_down, self.turned_on, self.turned_off]

        # One state per optional phase
        if self._has_start:
            variables.append(self.on_start)
        if self._has_stop:
            variables.append(self.stop)

        if self._has_flat:
            # entering ON_UP / ON_FLAT / ON_DOWN, and the gradients those entries release
            variables += [
                self.on_flat,
                self.stable,
                self.entered_up,
                self.entered_down,
                self.up_grad,
                self.aux_up_grad,
                self.down_grad,
                self.aux_down_grad,
            ]

        # Entering the shutdown ramp: from ON_FLAT via ON_DOWN with a plateau, which needs
        # the three-term marker, straight from ON_DOWN without, where dd_grad has no row.
        if self._has_stop and not self._has_flat:
            variables.append(self.down_to_stop_grad)
        if self._has_stop and self._has_flat:
            variables += [self.flat_down_stop, self.dd_grad]

        variables.append(self.power_level)
        return variables

    def _add_initial_variables(self, parameters: AbstractModuleParameters) -> None:
        """
        Leave the direction states to the solver on the step before the window.

        ON_UP, ON_DOWN and ON_FLAT at ``t`` describe the move from ``t`` to ``t + 1``, so on
        ``start_date - timestep`` they depend on the first power of the window: they cannot be
        read from the past dispatch. :meth:`_add_step_before_window` gives them their rows.
        """
        if not self._has_flat:
            return
        prev = parameters.temporal.start_date - parameters.temporal.timestep
        for variable in (self.on_up, self.on_down, self.on_flat, self.stable, self.entered_up, self.entered_down):
            variable.add(prev)
        if self._has_stop:
            self.dd_grad.add(prev)

    # ── Initial conditions ────────────────────────────────────────────────

    def _add_initial_conditions(self, parameters: AbstractModuleParameters) -> None:
        """
        Fix the state of the unit before the window, from its past dispatch.

        The past is read in three passes, each one from the previous only: the power, then
        the state the unit was in, then the transition markers as the rising edges of those
        states — the definition the constraints enforce inside the window.

        Only the values a constraint reads are fixed. The history reaches as far back as the
        deepest of them: the minimum times on and off counted from the end of their ramp, and
        with a plateau its minimum time and the two steps the plateau rows look back.

        :param parameters: Module parameters
        """
        temporal = parameters.temporal
        depth = max(self._T_on + self._T_start, self._T_off + self._T_stop, 1)
        if self._has_flat:
            depth = max(depth, self._T_stable - 1, 2)
        times: list[DateTime] = [temporal.start_date - k * temporal.timestep for k in range(depth, 0, -1)]

        power = self._initial_power(parameters, times)
        history = self._initial_states(times, power)
        history[self.power_level] = power
        for variable, values in history.items():
            # the direction states stop one step short of the window, zip stops with them
            for time, value in zip(times, values, strict=False):
                variable.fix(time, value)

        if self._has_flat:
            # up_grad(t) = (p(t) - p(t-1)) * on_up(t) * on_up(t-1). On the step before the window
            # only on_up(t) is still a solver variable, so the value fixed is linear in it.
            last, step = times[-1], power[-1] - power[-2]
            self.up_grad.fix(last, step * history[self.on_up][-1] * self.on_up[last])
            self.down_grad.fix(last, step * history[self.on_down][-1] * self.on_down[last])

    def _initial_power(self, parameters: AbstractModuleParameters, times: list[DateTime]) -> list[float]:
        """
        Read the past dispatch of the unit over *times*, 0 where there is none.

        A past dispatch that stops before ``start_date - timestep`` is discarded as a whole
        (day zero): the unit is then taken as off all along.
        """
        temporal = parameters.temporal
        past = (
            self._eq.power.get_forecast(temporal.execution_date, times[0], times[-1])
            if self._eq.power is not None
            else None
        )
        if past is None or past.last_date() != times[-1]:
            return [0.0] * len(times)
        return [past.get_value(time) if time in past else 0.0 for time in times]

    def _initial_states(self, times: list[DateTime], power: list[float]) -> dict[TemporalVariable, list[float]]:
        """
        Classify each past step from its power, and derive the transition markers from it.

        At or above ``minimum_power`` the unit was running, below it but producing it was on
        a ramp, at zero it was off. A unit without ramps has no middle regime: it runs as
        soon as it produces. A unit with both ramps tells them apart by the power trend, and
        is left on both when the trend is unknown — first step or flat power.

        :return: The fixed values of each temporal variable, aligned on *times*
        """
        has_ramps = self._has_start or self._has_stop
        both_ramps = self._has_start and self._has_stop
        off: list[float] = []
        running: list[float] = []
        start: list[float] = []
        stop: list[float] = []
        for k, (time, p) in enumerate(zip(times, power, strict=True)):
            runs = p >= self._eq.minimum_power.get_value(time) if has_ramps else p > 0
            ramps = not runs and p > 0
            trend = p - power[k - 1] if k else 0.0
            off.append(float(not runs and not ramps))
            running.append(float(runs))
            start.append(float(ramps and not (both_ramps and trend < 0)))
            stop.append(float(ramps and not (both_ramps and trend > 0)))

        history: dict[TemporalVariable, list[float]] = {
            self.off: off,
            self.turned_on: _rising_edges(start) if self._has_start else _rising_edges([1 - v for v in off]),
            self.turned_off: _rising_edges(stop) if self._has_stop else _rising_edges(off),
        }
        if self._has_start:
            history[self.on_start] = start
        if self._has_stop:
            history[self.stop] = stop

        if not self._has_flat:
            # A running unit is left free to move either way. These are constants, so mutual
            # exclusion does not bind them, and opening one alone would one-side the first
            # gradient row.
            history[self.on_up] = history[self.on_down] = running
            return history

        # the direction is the move to the next step: the last step before the window is the
        # solver's — see _add_initial_variables
        up = [runs * (p < p_next) for runs, p, p_next in zip(running, power, power[1:], strict=False)]
        down = [runs * (p > p_next) for runs, p, p_next in zip(running, power, power[1:], strict=False)]
        flat = [runs * (p == p_next) for runs, p, p_next in zip(running, power, power[1:], strict=False)]
        history |= {
            self.on_up: up,
            self.on_down: down,
            self.on_flat: flat,
            self.entered_up: _rising_edges(up),
            self.entered_down: _rising_edges(down),
            self.stable: _rising_edges(flat),
        }
        return history

    # ── Constraints ───────────────────────────────────────────────────────

    def _add_turned_on(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        ton = self.turned_on[time]
        off = self.off[time]
        off_prev = self.off[prev_time]
        n = self._eq.name
        model.add_constraint(ton <= 1 - off, f"t_on_evol_1_{time}_{n}")
        model.add_constraint(ton <= off_prev, f"t_on_evol_2_{time}_{n}")
        model.add_constraint(ton >= off_prev - off, f"t_on_evol_3_{time}_{n}")

    def _add_turned_off(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        toff = self.turned_off[time]
        n = self._eq.name
        if self._has_stop:
            stop = self.stop[time]
            stop_prev = self.stop[prev_time]
            model.add_constraint(toff <= 1 - stop_prev, f"t_off_evol_1_{time}_{n}")
            model.add_constraint(toff <= stop, f"t_off_evol_2_{time}_{n}")
            model.add_constraint(toff >= stop - stop_prev, f"t_off_evol_3_{time}_{n}")
        else:
            off = self.off[time]
            off_prev = self.off[prev_time]
            model.add_constraint(toff <= 1 - off_prev, f"t_off_evol_1_{time}_{n}")
            model.add_constraint(toff <= off, f"t_off_evol_2_{time}_{n}")
            model.add_constraint(toff >= off - off_prev, f"t_off_evol_3_{time}_{n}")

    def _add_stable(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        stab = self.stable[time]
        flat = self.on_flat[time]
        flat_prev = self.on_flat[prev_time]
        n = self._eq.name
        model.add_constraint(stab <= 1 - flat_prev, f"stable_evol_1_{time}_{n}")
        model.add_constraint(stab <= flat, f"stable_evol_2_{time}_{n}")
        model.add_constraint(stab >= flat - flat_prev, f"stable_evol_3_{time}_{n}")

    def _add_flat_down_stop(self, model: OptimisationModel, time: DateTime, prev_time: DateTime, ts: Duration) -> None:
        fds = self.flat_down_stop[time]
        stop = self.stop[time]
        on_down_prev = self.on_down[prev_time]
        flat_prev2 = self.on_flat[prev_time - ts]  # type: ignore[operator]
        n = self._eq.name
        # naming only
        prefix = "flat_down_stop_evol" if not self._has_start else "flat_down_stop"
        model.add_constraint(fds <= stop, f"{prefix}_1_{time}_{n}")
        model.add_constraint(fds <= on_down_prev, f"{prefix}_2_{time}_{n}")
        model.add_constraint(fds <= flat_prev2, f"{prefix}_3_{time}_{n}")
        model.add_constraint(fds >= stop + on_down_prev + flat_prev2 - 2, f"{prefix}_4_{time}_{n}")

    def _add_entered_up_down(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        eu = self.entered_up[time]
        on_up = self.on_up[time]
        on_up_prev = self.on_up[prev_time]
        ed = self.entered_down[time]
        on_down = self.on_down[time]
        on_down_prev = self.on_down[prev_time]
        n = self._eq.name
        model.add_constraint(eu <= 1 - on_up_prev, f"entered_up_evol_1_{time}_{n}")
        model.add_constraint(eu <= on_up, f"entered_up_evol_2_{time}_{n}")
        model.add_constraint(eu >= on_up - on_up_prev, f"entered_up_evol_3_{time}_{n}")
        model.add_constraint(ed <= 1 - on_down_prev, f"entered_down_evol_1_{time}_{n}")
        model.add_constraint(ed <= on_down, f"entered_down_evol_2_{time}_{n}")
        model.add_constraint(ed >= on_down - on_down_prev, f"entered_down_evol_3_{time}_{n}")

    def _add_gradient_auxiliaries(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        """
        Define the up/down gradient auxiliaries at *time*.

        Each one holds the power step when the unit is in the matching ON state and zero
        otherwise. A product of a variable by a state cannot be written directly, so
        it is expressed as four inequalities that are slack when the state is off and tight
        when it is on. ``swing`` is what makes them slack, so it has to be at least as
        large as any power step the unit can take, or the rows would forbid real dispatches.
        """
        n = self._eq.name
        swing = self._maximum_power_swing
        power = self.power_level[time]
        power_prev = self.power_level[prev_time]
        power_step = power - power_prev

        on_up_prev = self.on_up[prev_time]
        on_down_prev = self.on_down[prev_time]
        on_up = self.on_up[time]
        on_down = self.on_down[time]
        aux_up = self.aux_up_grad[time]
        aux_down = self.aux_down_grad[time]
        up_grad = self.up_grad[time]
        down_grad = self.down_grad[time]

        model.add_constraint(aux_up <= swing * on_up_prev, f"tilde_U_evol_1_{time}_{n}")
        model.add_constraint(aux_up >= -swing * on_up_prev, f"tilde_U_evol_2_{time}_{n}")
        model.add_constraint(aux_up <= power_step + swing * (1 - on_up_prev), f"tilde_U_evol_3_{time}_{n}")
        model.add_constraint(aux_up >= power_step - swing * (1 - on_up_prev), f"tilde_U_evol_4_{time}_{n}")
        model.add_constraint(aux_down <= swing * on_down_prev, f"tilde_D_evol_1_{time}_{n}")
        model.add_constraint(aux_down >= -swing * on_down_prev, f"tilde_D_evol_2_{time}_{n}")
        model.add_constraint(aux_down <= power_step + swing * (1 - on_down_prev), f"tilde_D_evol_3_{time}_{n}")
        model.add_constraint(aux_down >= power_step - swing * (1 - on_down_prev), f"tilde_D_evol_4_{time}_{n}")
        model.add_constraint(up_grad <= swing * on_up, f"U_evol_1_{time}_{n}")
        model.add_constraint(up_grad >= -swing * on_up, f"U_evol_2_{time}_{n}")
        model.add_constraint(up_grad <= aux_up + swing * (1 - on_up), f"U_evol_3_{time}_{n}")
        model.add_constraint(up_grad >= aux_up - swing * (1 - on_up), f"U_evol_4_{time}_{n}")
        model.add_constraint(down_grad <= swing * on_down, f"D_evol_1_{time}_{n}")
        model.add_constraint(down_grad >= -swing * on_down, f"D_evol_2_{time}_{n}")
        model.add_constraint(down_grad <= aux_down + swing * (1 - on_down), f"D_evol_3_{time}_{n}")
        model.add_constraint(down_grad >= aux_down - swing * (1 - on_down), f"D_evol_4_{time}_{n}")

    def _add_down_to_stop_evol(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        """
        Define ``down_to_stop_grad`` as the ON_DOWN → STOP transition at *time*.

        The gradient constraints lean on it to release the extra downward slope the unit
        needs on the step where it leaves ON_DOWN and enters its shutdown ramp, so the
        auxiliary must track exactly that event: ``stop(t) AND on_down(t-1)``.
        """
        n = self._eq.name
        dts = self.down_to_stop_grad[time]
        stop = self.stop[time]
        on_down_prev = self.on_down[prev_time]
        model.add_constraint(dts <= stop, f"down_to_stop_evol_1_{time}_{n}")
        model.add_constraint(dts <= on_down_prev, f"down_to_stop_evol_2_{time}_{n}")
        model.add_constraint(dts >= stop + on_down_prev - 1, f"down_to_stop_evol_3_{time}_{n}")

    def _state_vars(self) -> dict[str, TemporalVariable]:
        """
        Map each state name used in :attr:`_BANNED_TRANSITIONS` to its temporal variable.

        :return: State name to variable
        """
        return {
            "off": self.off,
            "on_start": self.on_start,
            "on_up": self.on_up,
            "on_flat": self.on_flat,
            "on_down": self.on_down,
            "stop": self.stop,
        }

    def _add_mutual_exclusion(self, model: OptimisationModel, time: DateTime) -> None:
        n = self._eq.name
        expr = self.off[time] + self.on_up[time] + self.on_down[time]
        if self._has_flat:
            expr = expr + self.on_flat[time]
        if self._has_stop:
            expr = expr + self.stop[time]
        if self._has_start:
            expr = expr + self.on_start[time]
        model.add_constraint(expr == 1, f"mutual_exclusion_{time}_{n}")

    def _add_step_before_window(self, model: OptimisationModel, prev_time: DateTime, ts: Duration) -> None:
        """
        Emit on the step before the window the per-step rows its solver variables need.

        With a plateau the direction states and their markers are solver variables on
        ``start_date - timestep`` too — see :meth:`_add_initial_variables` — so they get the
        same rows as inside the window, or the solver would be free to set them to anything.
        The rows read the step before, fixed: the temporal variables serve constants there,
        so the rows mixing only constants are degenerate, not wrong.

        :param model: The optimisation model
        :param prev_time: One step before the window
        :type prev_time: DateTime
        :param ts: Duration of one timestep
        :type ts: Duration
        """
        prev2 = prev_time - ts  # type: ignore[operator]
        self._add_stable(model, prev_time, prev2)
        self._add_entered_up_down(model, prev_time, prev2)
        self._add_mutual_exclusion(model, prev_time)
        self._add_transition_constraints(model, prev_time, prev2, only=self._BOUNDARY_BANS)
        self._add_minimum_time_on(model, prev_time, ts)
        self._add_minimum_time_stable(model, prev_time, ts)

    def _add_transition_constraints(
        self,
        model: OptimisationModel,
        time: DateTime,
        prev_time: DateTime,
        only: tuple[tuple[str, str], ...] | None = None,
    ) -> None:
        """
        Ban the state changes the unit's machine cannot make — see :attr:`_BANNED_TRANSITIONS`.

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param prev_time: Previous timestep
        :type prev_time: DateTime
        :param only: Emit these bans only, when the machine has them. A ban keeps its number
            in the table either way.
        :type only: tuple[tuple[str, str], ...] | None
        """
        n = self._eq.name
        states = self._state_vars()
        bans = self._BANNED_TRANSITIONS[self._has_stop, self._has_start, self._has_flat]
        for index, (from_state, to_state) in enumerate(bans, start=1):
            if only is not None and (from_state, to_state) not in only:
                continue
            model.add_constraint(
                states[from_state][prev_time] + states[to_state][time] <= 1,
                f"transition_constraint_{index}_{time}_{n}",
            )

    def _add_eviction_constraints(
        self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters
    ) -> None:
        """
        Forbid re-entering a ramp before the previous one has run its course.

        The ramp lasts exactly ``T_stop`` (resp. ``T_start``) steps counting the one the
        unit turned off (resp. on) on. The anchor can land before the window, where
        ``turned_off`` is a constant and the row degenerates to ``stop(t) <= 1``.

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param parameters: Module parameters
        """
        n = self._eq.name
        ts = parameters.temporal.timestep
        if self._has_stop:
            stop = self.stop[time]
            evict_stop = time - self._T_stop * ts
            toff_evict = self.turned_off[evict_stop]
            label = "stop_eviction_constraint" if self._has_start else "eviction_constraint"
            model.add_constraint(toff_evict + stop <= 1, f"{label}_{time}_{n}")
        if self._has_start:
            start = self.on_start[time]
            evict_start = time - self._T_start * ts
            ton_evict = self.turned_on[evict_start]
            label = "start_eviction_constraint" if self._has_stop else "eviction_constraint"
            model.add_constraint(ton_evict + start <= 1, f"{label}_{time}_{n}")

    def _add_minimum_time_constraints(
        self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters
    ) -> None:
        n = self._eq.name
        ts = parameters.temporal.timestep
        stop_offset = self._T_stop if self._has_stop else 0

        self._add_minimum_time_on(model, time, ts)

        if self._T_off >= 2:
            for steps_back in range(1, self._T_off):
                local_time = time - (steps_back + stop_offset) * ts
                model.add_constraint(
                    self.turned_off[local_time] <= self.off[time],
                    f"minimum_time_off_{n}_{local_time}_{time}",
                )

        self._add_minimum_time_stable(model, time, ts)

        if self._has_stop and self._T_stop >= 2:
            stop = self.stop[time]
            for steps_back in range(1, self._T_stop - 1):
                local_time = time - steps_back * ts
                model.add_constraint(
                    self.turned_off[local_time] <= stop,
                    f"shutdown_ramp_{n}_{local_time}_{time}",
                )

        if self._has_start and self._T_start >= 2:
            start = self.on_start[time]
            # naming only; the stray underscore is in the LP references
            prefix = "startup_ramp" if not self._has_flat else "start_up_ramp"
            for steps_back in range(1, self._T_start - 1):
                local_time = time - steps_back * ts
                model.add_constraint(
                    self.turned_on[local_time] <= start,
                    f"{prefix}_{n}_{local_time}_{time}",
                )

    def _add_minimum_time_on(self, model: OptimisationModel, time: DateTime, ts: Duration) -> None:
        """Keep the unit on for ``T_on`` steps once its startup ramp is over."""
        if self._T_on < 2:
            return
        n = self._eq.name
        start_offset = self._T_start if self._has_start else 0
        on_expr = self.on_up[time] + self.on_down[time]
        if self._has_flat:
            on_expr = on_expr + self.on_flat[time]
        for steps_back in range(1, self._T_on):
            local_time = time - (steps_back + start_offset) * ts
            model.add_constraint(
                self.turned_on[local_time] <= on_expr,
                f"minimum_time_on_{n}_{local_time}_{time}",
            )

    def _add_minimum_time_stable(self, model: OptimisationModel, time: DateTime, ts: Duration) -> None:
        """Keep the unit on its plateau for ``T_stable`` steps once it has entered it."""
        if not self._has_flat or self._T_stable < 2:
            return
        n = self._eq.name
        on_flat = self.on_flat[time]
        for steps_back in range(1, self._T_stable - 1):
            local_time = time - steps_back * ts
            model.add_constraint(
                self.stable[local_time] <= on_flat,
                f"minimum_time_stable_{n}_{local_time}_{time}",
            )

    def _add_power_bounds(self, model: OptimisationModel, time: DateTime) -> None:
        n = self._eq.name
        p = self.power_level[time]
        max_p = self._eq.maximum_power.get_value(time)
        min_p = self._eq.minimum_power.get_value(time)
        q_min = self._eq.minimum_power.max()
        on_up = self.on_up[time]
        on_down = self.on_down[time]
        on_sum = on_up + on_down
        if self._has_flat:
            on_sum = on_sum + self.on_flat[time]

        lb = min_p * on_sum
        ub = max_p * on_sum

        if self._has_stop:
            q_step_down = q_min / self._T_stop
            toff = self.turned_off[time]
            stop = self.stop[time]
            lb = lb + toff * (q_min - q_step_down)
            ub = ub + stop * q_min - toff * q_step_down

        if self._has_start:
            start = self.on_start[time]
            ub = ub + start * q_min

        model.add_constraint(p >= lb, f"lower_bound_{n}_{time}")
        model.add_constraint(p <= ub, f"upper_bound_{n}_{time}")

    def _add_dd_constraints(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        n = self._eq.name
        swing = self._maximum_power_swing
        stop = self.stop[time]
        dd_prev = self.dd_grad[prev_time]
        d_prev = self.down_grad[prev_time]
        model.add_constraint(dd_prev <= swing * stop, f"DD_evol_1_{time}_{n}")
        model.add_constraint(dd_prev >= -swing * stop, f"DD_evol_2_{time}_{n}")
        model.add_constraint(dd_prev <= d_prev + swing * (1 - stop), f"DD_evol_3_{time}_{n}")
        model.add_constraint(dd_prev >= d_prev - swing * (1 - stop), f"DD_evol_4_{time}_{n}")

    def _add_gradient_constraints(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        """
        Bound the power step: ``down_bound <= p(t) - p(t-1) <= up_bound``.

        Both bounds start from the unit's gradient limit and are widened, term by term, by
        each event that legitimately lets the unit move further on this step: holding an ON
        state, firing a ramp increment, or leaving ON_DOWN for the shutdown ramp. With no
        gradient limit there is nothing to enforce and ``swing`` stands in — hence the
        ``unconstrained_*`` naming.

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param prev_time: Previous timestep
        :type prev_time: DateTime
        """
        n = self._eq.name
        delta_q = self._Delta_Q
        swing = self._maximum_power_swing
        ramp_allowance = delta_q if delta_q > 0 else swing

        p = self.power_level[time]
        p_prev = self.power_level[prev_time]
        power_step = p - p_prev

        ton = self.turned_on[time]
        toff = self.turned_off[time]

        if self._has_flat:
            entered_up_prev = self.entered_up[prev_time]
            entered_down_prev = self.entered_down[prev_time]
            u_prev = self.up_grad[prev_time]
            d_prev = self.down_grad[prev_time]
            up_bound = ramp_allowance * entered_up_prev + u_prev + d_prev
            down_bound = -ramp_allowance * entered_down_prev + u_prev + d_prev
        else:
            on_up_prev = self.on_up[prev_time]
            on_down_prev = self.on_down[prev_time]
            up_bound = ramp_allowance * on_up_prev
            down_bound = -ramp_allowance * on_down_prev

        q_min = self._eq.minimum_power.max()

        if self._has_start:
            q_step_up = q_min / self._T_start
            start_prev = self.on_start[prev_time]
            startup_contrib = q_step_up * ton + start_prev * q_step_up
            up_bound = up_bound + startup_contrib
            down_bound = down_bound + startup_contrib
        else:
            up_bound = up_bound + swing * ton

        if self._has_stop:
            q_step_down = q_min / self._T_stop
            stop_prev = self.stop[prev_time]
            shutdown_contrib = -toff * q_step_down - stop_prev * q_step_down
            up_bound = up_bound + shutdown_contrib
            down_bound = down_bound + shutdown_contrib
            if self._has_flat:
                fds = self.flat_down_stop[time]
                dd_prev = self.dd_grad[prev_time]
                down_bound = down_bound + fds * ramp_allowance - dd_prev
                up_bound = up_bound - dd_prev
            else:
                down_to_stop = self.down_to_stop_grad[time]
                down_bound = down_bound + down_to_stop * ramp_allowance
        else:
            down_bound = down_bound - swing * toff

        up_prefix = "upward_gradient" if delta_q > 0 else "unconstrained_upward_gradient"
        down_prefix = "downward_gradient" if delta_q > 0 else "unconstrained_downward_gradient"

        # naming only: two configurations down_prefix the row with the previous timestep
        if not self._has_stop and not self._has_start and not self._has_flat:
            grad_time = prev_time
        elif self._has_start and not self._has_stop and not self._has_flat and delta_q == 0:
            grad_time = prev_time
        else:
            grad_time = time

        model.add_constraint(power_step <= up_bound, f"{up_prefix}_{n}_{grad_time}")
        model.add_constraint(power_step >= down_bound, f"{down_prefix}_{n}_{grad_time}")


def _rising_edges(states: list[float]) -> list[float]:
    """
    Mark each step a 0/1 state sequence switches on.

    The first step is never marked: what came before it is unknown.

    >>> _rising_edges([0, 1, 1, 0, 1])
    [0.0, 1.0, 0.0, 0.0, 1.0]
    """
    return [0.0] + [float(now > before) for before, now in zip(states, states[1:], strict=False)]
