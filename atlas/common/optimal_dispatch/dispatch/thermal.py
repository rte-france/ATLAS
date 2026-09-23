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
from atlas.common.optimal_dispatch.dispatch.thermal_initial_conditions import ThermalInitialConditions
from atlas.math.timeseries import Timeseries
from atlas.solver.model_var import ModelVar
from atlas.solver.solver_interface import OptimisationModel

if TYPE_CHECKING:
    from atlas.common.optimal_dispatch.input_objects.thermal import ThermalDispatchInput


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
    conditions and stored as a plain float in the :class:`ModelVar` extended frame. Inside
    the window it is a decision variable. ``ModelVar.get_value`` hides the difference, so a
    constraint reaching across the boundary silently mixes constants and variables.

    That boundary is where this model is hardest to get right — a row anchored before
    ``start_date`` degenerates instead of binding, and mutual exclusion does not apply
    between constants. :meth:`_add_initial_boundary_constraints`,
    :meth:`_add_eviction_constraints` and the ``time == start_date`` branches of
    :meth:`_add_minimum_time_constraints` all live on it.

    Typical usage::

        dispatch = ThermalDispatch(equipment)
        dispatch.setup(model, parameters)                 # init vars + initial conditions
        for time in time_window:
            dispatch.add_variables(time)                  # per-timestep decision variables
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

        # ModelVar placeholders — all wired by _setup_state_variables(), which groups them
        # the same way and documents what each group is for.

        # States — exactly one of these is 1 at any timestep
        self.off_var: ModelVar = None  # type: ignore[assignment]
        self.on_start_var: ModelVar = None  # type: ignore[assignment]
        self.on_up_var: ModelVar = None  # type: ignore[assignment]
        self.on_flat_var: ModelVar = None  # type: ignore[assignment]
        self.on_down_var: ModelVar = None  # type: ignore[assignment]
        self.stop_var: ModelVar = None  # type: ignore[assignment]

        # Transition markers — fire on the step the unit enters the matching state
        self.turned_on: ModelVar = None  # type: ignore[assignment]
        self.turned_off: ModelVar = None  # type: ignore[assignment]
        self.entered_up_var: ModelVar = None  # type: ignore[assignment]
        self.entered_down_var: ModelVar = None  # type: ignore[assignment]
        self.stable_var: ModelVar = None  # type: ignore[assignment]
        self.flat_down_stop: ModelVar = None  # type: ignore[assignment]
        self.down_to_stop_grad: ModelVar = None  # type: ignore[assignment]

        # Gradient auxiliaries — linearised products of a power step by a state
        self.up_grad_var: ModelVar = None  # type: ignore[assignment]
        self.down_grad_var: ModelVar = None  # type: ignore[assignment]
        self.aux_up_grad_var: ModelVar = None  # type: ignore[assignment]
        self.aux_down_grad_var: ModelVar = None  # type: ignore[assignment]
        self.dd_grad_var: ModelVar = None  # type: ignore[assignment]

        # The dispatch
        self.power_level_var: ModelVar = None  # type: ignore[assignment]

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
        Compute time parameters, create ModelVar objects, and apply initial conditions.

        Must be called before :meth:`add_variables` or :meth:`add_constraints`.

        :param model: The optimisation model
        :param parameters: Module parameters — must expose ``temporal.timestep``,
            ``temporal.start_date``, ``temporal.end_date``, ``temporal.execution_date``
        """
        self._compute_time_parameters(parameters)
        self._setup_state_variables(model)
        self._add_initial_variables(parameters)
        self._add_initial_conditions(parameters)

    def add_variables(self, time: DateTime) -> None:
        """
        Register decision variables for *time* in the model.

        :param time: The timestep for which to create variables
        :type time: DateTime
        """
        self.off_var.set_model_var(time)
        self.on_up_var.set_model_var(time)
        self.on_down_var.set_model_var(time)
        self.turned_on.set_model_var(time)
        self.turned_off.set_model_var(time)

        if self._has_start:
            self.on_start_var.set_model_var(time)
        if self._has_stop:
            self.stop_var.set_model_var(time)

        if self._has_flat:
            self.on_flat_var.set_model_var(time)
            self.stable_var.set_model_var(time)
            self.entered_up_var.set_model_var(time)
            self.entered_down_var.set_model_var(time)
            self.up_grad_var.set_model_var(time)
            self.aux_up_grad_var.set_model_var(time)
            self.down_grad_var.set_model_var(time)
            self.aux_down_grad_var.set_model_var(time)

        # Entering the shutdown ramp: from ON_FLAT via ON_DOWN with a plateau, which needs
        # the three-term marker, straight from ON_DOWN without, where dd_grad has no row.
        if self._has_stop and not self._has_flat:
            self.down_to_stop_grad.set_model_var(time)
        if self._has_stop and self._has_flat:
            self.flat_down_stop.set_model_var(time)
            self.dd_grad_var.set_model_var(time)

        self.power_level_var.set_model_var(time)

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
            self._add_initial_boundary_constraints(model, time, prev_time, ts)

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
                sum(self.power_level_var.get_value(t) for t in steps)
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

    def _boolean_var(self, model: OptimisationModel, template: str) -> ModelVar:
        """
        Build a boolean :class:`ModelVar` whose LP name is *template*.

        :param model: The optimisation model
        :param template: Name pattern, formatted with ``n`` (unit name) and ``time``
        :return: The wired ModelVar
        """

        def name(time: DateTime) -> str:
            return template.format(n=self._eq.name, time=time)

        return ModelVar(
            getter=lambda time: model.get_variable(name(time)),
            setter=lambda time: model.add_boolean_variable(name(time)),
        )

    def _swing_bounded_var(self, model: OptimisationModel, template: str) -> ModelVar:
        """
        Build a continuous :class:`ModelVar` bounded by ±:attr:`_maximum_power_swing`.

        The bound is read when the variable is created, not here, so it picks up the value
        :meth:`_compute_time_parameters` has already stored.

        :param model: The optimisation model
        :param template: Name pattern, formatted with ``n`` (unit name) and ``time``
        :return: The wired ModelVar
        """

        def name(time: DateTime) -> str:
            return template.format(n=self._eq.name, time=time)

        return ModelVar(
            getter=lambda time: model.get_variable(name(time)),
            setter=lambda time: model.add_continuous_variable(
                name(time), -self._maximum_power_swing, self._maximum_power_swing
            ),
        )

    def _setup_state_variables(self, model: OptimisationModel) -> None:
        eq = self._eq
        n = eq.name

        # States — on_flat, on_start and stop only get a model variable when their phase exists
        self.off_var = self._boolean_var(model, "off_{n}_{time}")
        self.on_start_var = self._boolean_var(model, "on_start_{n}_{time}")
        self.on_up_var = self._boolean_var(model, "on_up_{n}_{time}")
        self.on_flat_var = self._boolean_var(model, "on_flat_{n}_{time}")
        self.on_down_var = self._boolean_var(model, "on_down_{n}_{time}")
        self.stop_var = self._boolean_var(model, "stop_{n}_{time}")

        # Transition markers. The layouts disagree with the states above — name before the
        # timestamp there, after it here. Load-bearing: the LP references carry both.
        self.turned_on = self._boolean_var(model, "t_on_{n}_{time}")
        self.turned_off = self._boolean_var(model, "t_off_{n}_{time}")
        self.entered_up_var = self._boolean_var(model, "entered_up_{time}_{n}")
        self.entered_down_var = self._boolean_var(model, "entered_down_{time}_{n}")
        self.stable_var = self._boolean_var(model, "stable_{time}_{n}")
        self.flat_down_stop = self._boolean_var(model, "flat_down_stop_{time}_{n}")
        self.down_to_stop_grad = self._boolean_var(model, "down_to_stop_grad_{time}_{n}")

        # Gradient auxiliaries — products of a power step by a state, linearised below
        self.up_grad_var = self._swing_bounded_var(model, "up_grad_{time}_{n}")
        self.down_grad_var = self._swing_bounded_var(model, "down_grad_{time}_{n}")
        self.aux_up_grad_var = self._swing_bounded_var(model, "aux_up_grad_{time}_{n}")
        self.aux_down_grad_var = self._swing_bounded_var(model, "aux_down_grad_{time}_{n}")
        self.dd_grad_var = self._swing_bounded_var(model, "dd_grad_{time}_{n}")

        # Alone in taking a time-varying bound, hence written out
        self.power_level_var = ModelVar(
            getter=lambda time: model.get_variable(f"{n}_power_level_{time}"),
            setter=lambda time: model.add_continuous_variable(
                f"{n}_power_level_{time}", 0, eq.maximum_power.get_value(time)
            ),
        )

    def _add_initial_variables(self, parameters: AbstractModuleParameters) -> None:
        temporal = parameters.temporal
        prev = temporal.start_date - temporal.timestep
        if self._T_stable >= 1:
            self.on_up_var.set_model_var(prev)
            self.on_down_var.set_model_var(prev)
            self.on_flat_var.set_model_var(prev)
            self.stable_var.set_model_var(prev)
            self.entered_up_var.set_model_var(prev)
            self.entered_down_var.set_model_var(prev)
        if self._T_stable >= 1 and self._T_stop >= 1:
            self.dd_grad_var.set_model_var(prev)

    # ── Initial conditions ────────────────────────────────────────────────

    def _add_initial_conditions(self, parameters: AbstractModuleParameters) -> None:
        ic = self._build_initial_conditions(parameters)
        if ic.day_zero:
            self._init_day_zero(parameters, ic)
        else:
            self._init_from_previous(parameters, ic)

    def _build_initial_conditions(self, parameters: AbstractModuleParameters) -> ThermalInitialConditions:
        eq = self._eq
        temporal = parameters.temporal
        T_traceback = max(self._T_on + self._T_start, self._T_off + self._T_stop)

        initial_times: list[DateTime] = []
        stable_initial_times: list[DateTime] = []
        if T_traceback > 0:
            for k in range(T_traceback, 0, -1):
                initial_times.append(temporal.start_date - k * temporal.timestep)
        else:
            initial_times.append(temporal.start_date - temporal.timestep)
        for k in range(T_traceback, 1, -1):
            stable_initial_times.append(temporal.start_date - k * temporal.timestep)

        power_ts = (
            eq.power.get_forecast(temporal.execution_date, initial_times[0], initial_times[-1])
            if eq.power is not None
            else None
        )

        day_zero = power_ts is None
        if power_ts is not None:
            if temporal.start_date - temporal.timestep != power_ts.last_date():
                day_zero = True

        return ThermalInitialConditions(
            initial_times=initial_times,
            stable_initial_times=stable_initial_times,
            power_ts=power_ts,
            day_zero=day_zero,
        )

    def _init_day_zero(self, parameters: AbstractModuleParameters, ic: ThermalInitialConditions) -> None:
        for time in ic.initial_times:
            self._init_day_zero_core(time)
            if not self._has_flat:
                self._init_day_zero_on_states(time)
            else:
                self._init_day_zero_gradient_vars(time)
            if self._has_stop:
                self.stop_var.set_extended(time, 0)
                if not self._has_flat:
                    self.down_to_stop_grad.set_extended(time, 0)
                else:
                    self.flat_down_stop.set_extended(time, 0)
            if self._has_start:
                self.on_start_var.set_extended(time, 0)

        for time in ic.stable_initial_times:
            self._init_day_zero_stable_vars(time)

        if self._has_flat and not self._has_stop and not self._has_start:
            if isinstance(ic.power_ts, Timeseries):
                self._init_gradient_initial_conditions(parameters)

    def _init_from_previous(self, parameters: AbstractModuleParameters, ic: ThermalInitialConditions) -> None:
        if not isinstance(ic.power_ts, Timeseries):
            raise ValueError("power_ts is required when day_zero is False")

        for time in ic.initial_times:
            self._init_one_time(parameters, ic.extended_start_date, time, ic.power_ts)

        if self._has_flat:
            self._init_stable_times(parameters, ic)
            self._init_gradient_initial_conditions(parameters)

    def _init_one_time(
        self,
        parameters: AbstractModuleParameters,
        extended_start_date: DateTime,
        time: DateTime,
        power_ts: Timeseries,
    ) -> None:
        """
        Pin the unit's state one step before the window, from its past dispatch.

        Everything set here is a constant in the extended frame. The measured power selects
        one of three regimes, in the order the branches below take them: at or above
        ``minimum_power`` the unit was in an ON state; producing below it, it was on a ramp;
        zero, it was off. A unit without ramps has no middle regime.

        Both ON states are set for a running unit: these are constants, so mutual exclusion
        does not apply, and setting one alone would one-side the first gradient row.

        :param parameters: Module parameters
        :param extended_start_date: First timestep held in the extended frame
        :type extended_start_date: DateTime
        :param time: Timestep to initialise
        :type time: DateTime
        :param power_ts: Past dispatch of the unit
        :type power_ts: Timeseries
        """
        ts = parameters.temporal.timestep
        if time in power_ts:
            power_t = power_ts.get_value(time)
            self.power_level_var.set_extended(time, power_t)

            if self._has_start or self._has_stop:
                min_power = self._eq.minimum_power.get_value(time)
                if power_t >= min_power:
                    self.off_var.set_extended(time, 0)
                    if self._has_stop:
                        self.stop_var.set_extended(time, 0)
                    if self._has_start:
                        self.on_start_var.set_extended(time, 0)
                    if not self._has_flat:
                        self.on_up_var.set_extended(time, 1)
                        self.on_down_var.set_extended(time, 1)
                elif power_t > 0:
                    self.off_var.set_extended(time, 0)
                    if self._has_stop:
                        self.stop_var.set_extended(time, 1)
                    if self._has_start:
                        self.on_start_var.set_extended(time, 1)
                    if not self._has_flat:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 0)
                else:
                    self.off_var.set_extended(time, 1)
                    if self._has_stop:
                        self.stop_var.set_extended(time, 0)
                    if self._has_start:
                        self.on_start_var.set_extended(time, 0)
                    if not self._has_flat:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 0)
            else:
                if power_t > 0:
                    self.off_var.set_extended(time, 0)
                    if not self._has_flat:
                        # a unit with no ramp phase and no stable phase enters the window
                        # free to move either way, as in the online branch above
                        self.on_up_var.set_extended(time, 1)
                        self.on_down_var.set_extended(time, 1)
                else:
                    self.power_level_var.set_extended(time, 0)
                    self.off_var.set_extended(time, 1)
                    if not self._has_flat:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 0)
        else:
            self.power_level_var.set_extended(time, 0)
            self.off_var.set_extended(time, 1)
            if self._has_stop:
                self.stop_var.set_extended(time, 0)
            if self._has_start:
                self.on_start_var.set_extended(time, 0)
            if not self._has_flat:
                self.on_up_var.set_extended(time, 0)
                self.on_down_var.set_extended(time, 0)

        self.turned_on.set_extended(time, 0)
        self.turned_off.set_extended(time, 0)
        if self._has_stop and not self._has_flat:
            self.down_to_stop_grad.set_extended(time, 0)

        if time == extended_start_date:
            return

        prev_time = time - ts

        if self._has_start and self._has_stop and time in power_ts:
            power_t = power_ts.get_value(time)
            prev_power = power_ts.get_value(prev_time) if prev_time in power_ts else 0
            if self.on_start_var.get_extended_value(time) == 1:
                if power_t > prev_power:
                    self.stop_var.set_extended(time, 0)
                elif power_t < prev_power:
                    self.stop_var.set_extended(time, 1)
                    self.on_start_var.set_extended(time, 0)

        if self._has_stop:
            if self.stop_var.get_extended_value(time) - self.stop_var.get_extended_value(prev_time) == 1:
                self.turned_off.set_extended(time, 1)
        else:
            if self.off_var.get_extended_value(time) - self.off_var.get_extended_value(prev_time) == 1:
                self.turned_off.set_extended(time, 1)

        if self._has_start:
            if self.on_start_var.get_extended_value(time) - self.on_start_var.get_extended_value(prev_time) == 1:
                self.turned_on.set_extended(time, 1)
        else:
            if self.off_var.get_extended_value(time) - self.off_var.get_extended_value(prev_time) == -1:
                self.turned_on.set_extended(time, 1)

        if self._has_stop and not self._has_flat:
            if self.stop_var.get_extended_value(time) - self.on_down_var.get_extended_value(prev_time) == 0:
                self.down_to_stop_grad.set_extended(time, 1)

    def _init_stable_times(self, parameters: AbstractModuleParameters, ic: ThermalInitialConditions) -> None:
        ts = parameters.temporal.timestep
        for time in ic.stable_initial_times:
            next_time = time + ts
            current_power = self.power_level_var.get_extended_value(time)
            next_power = self.power_level_var.get_extended_value(next_time)

            self.stable_var.set_extended(time, 0)
            self.entered_up_var.set_extended(time, 0)
            self.entered_down_var.set_extended(time, 0)

            if self.off_var.get_extended_value(time) == 0:
                in_ramp = (self._has_stop and self.stop_var.get_extended_value(time) == 1) or (
                    self._has_start and self.on_start_var.get_extended_value(time) == 1
                )
                if in_ramp:
                    self.on_up_var.set_extended(time, 0)
                    self.on_down_var.set_extended(time, 0)
                    self.on_flat_var.set_extended(time, 0)
                else:
                    if current_power < next_power:
                        self.on_up_var.set_extended(time, 1)
                        self.on_down_var.set_extended(time, 0)
                        self.on_flat_var.set_extended(time, 0)
                    elif current_power > next_power:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 1)
                        self.on_flat_var.set_extended(time, 0)
                    else:
                        self.on_up_var.set_extended(time, 0)
                        self.on_down_var.set_extended(time, 0)
                        self.on_flat_var.set_extended(time, 1)
            else:
                self.on_up_var.set_extended(time, 0)
                self.on_down_var.set_extended(time, 0)
                self.on_flat_var.set_extended(time, 0)

            if time != ic.extended_start_date and self.off_var.get_extended_value(time) != 1:
                prev_time = time - ts
                if self.on_flat_var.get_extended_value(time) - self.on_flat_var.get_extended_value(prev_time) == 1:
                    self.stable_var.set_extended(time, 1)
                if self.on_up_var.get_extended_value(time) - self.on_up_var.get_extended_value(prev_time) == 1:
                    self.entered_up_var.set_extended(time, 1)
                if self.on_down_var.get_extended_value(time) - self.on_down_var.get_extended_value(prev_time) == 1:
                    self.entered_down_var.set_extended(time, 1)

    def _init_gradient_initial_conditions(self, parameters: AbstractModuleParameters) -> None:
        temporal = parameters.temporal
        t_minus_one = temporal.start_date - temporal.timestep
        t_minus_two = temporal.start_date - 2 * temporal.timestep

        power_minus_one = self.power_level_var.get_value(t_minus_one)
        power_minus_two = self.power_level_var.get_value(t_minus_two)
        power_diff = power_minus_one - power_minus_two

        self.up_grad_var.set_extended(
            t_minus_one,
            power_diff * self.on_up_var.get_value(t_minus_one) * self.on_up_var.get_value(t_minus_two),
        )
        self.down_grad_var.set_extended(
            t_minus_one,
            power_diff * self.on_down_var.get_value(t_minus_one) * self.on_down_var.get_value(t_minus_two),
        )

    # ── Day-zero helpers ──────────────────────────────────────────────────

    def _init_day_zero_core(self, time: DateTime) -> None:
        self.off_var.set_extended(time, 1)
        self.turned_on.set_extended(time, 0)
        self.turned_off.set_extended(time, 0)
        self.power_level_var.set_extended(time, 0)

    def _init_day_zero_on_states(self, time: DateTime) -> None:
        self.on_up_var.set_extended(time, 0)
        self.on_down_var.set_extended(time, 0)

    def _init_day_zero_gradient_vars(self, time: DateTime) -> None:
        self.up_grad_var.set_extended(time, 0)
        self.down_grad_var.set_extended(time, 0)
        self.aux_up_grad_var.set_extended(time, 0)
        self.aux_down_grad_var.set_extended(time, 0)

    def _init_day_zero_stable_vars(self, time: DateTime) -> None:
        self.on_flat_var.set_extended(time, 0)
        self.on_up_var.set_extended(time, 0)
        self.on_down_var.set_extended(time, 0)
        self.stable_var.set_extended(time, 0)
        self.entered_up_var.set_extended(time, 0)
        self.entered_down_var.set_extended(time, 0)

    # ── Constraints ───────────────────────────────────────────────────────

    def _add_turned_on(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        ton = self.turned_on.get_value(time)
        off = self.off_var.get_value(time)
        off_prev = self.off_var.get_value(prev_time)
        n = self._eq.name
        model.add_constraint(ton <= 1 - off, f"t_on_evol_1_{time}_{n}")
        model.add_constraint(ton <= off_prev, f"t_on_evol_2_{time}_{n}")
        model.add_constraint(ton >= off_prev - off, f"t_on_evol_3_{time}_{n}")

    def _add_turned_off(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        toff = self.turned_off.get_value(time)
        n = self._eq.name
        if self._has_stop:
            stop = self.stop_var.get_value(time)
            stop_prev = self.stop_var.get_value(prev_time)
            model.add_constraint(toff <= 1 - stop_prev, f"t_off_evol_1_{time}_{n}")
            model.add_constraint(toff <= stop, f"t_off_evol_2_{time}_{n}")
            model.add_constraint(toff >= stop - stop_prev, f"t_off_evol_3_{time}_{n}")
        else:
            off = self.off_var.get_value(time)
            off_prev = self.off_var.get_value(prev_time)
            model.add_constraint(toff <= 1 - off_prev, f"t_off_evol_1_{time}_{n}")
            model.add_constraint(toff <= off, f"t_off_evol_2_{time}_{n}")
            model.add_constraint(toff >= off - off_prev, f"t_off_evol_3_{time}_{n}")

    def _add_stable(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        stab = self.stable_var.get_value(time)
        flat = self.on_flat_var.get_value(time)
        flat_prev = self.on_flat_var.get_value(prev_time)
        n = self._eq.name
        model.add_constraint(stab <= 1 - flat_prev, f"stable_evol_1_{time}_{n}")
        model.add_constraint(stab <= flat, f"stable_evol_2_{time}_{n}")
        model.add_constraint(stab >= flat - flat_prev, f"stable_evol_3_{time}_{n}")

    def _add_flat_down_stop(self, model: OptimisationModel, time: DateTime, prev_time: DateTime, ts: Duration) -> None:
        fds = self.flat_down_stop.get_value(time)
        stop = self.stop_var.get_value(time)
        on_down_prev = self.on_down_var.get_value(prev_time)
        flat_prev2 = self.on_flat_var.get_value(prev_time - ts)  # type: ignore[operator]
        n = self._eq.name
        # naming only
        prefix = "flat_down_stop_evol" if not self._has_start else "flat_down_stop"
        model.add_constraint(fds <= stop, f"{prefix}_1_{time}_{n}")
        model.add_constraint(fds <= on_down_prev, f"{prefix}_2_{time}_{n}")
        model.add_constraint(fds <= flat_prev2, f"{prefix}_3_{time}_{n}")
        model.add_constraint(fds >= stop + on_down_prev + flat_prev2 - 2, f"{prefix}_4_{time}_{n}")

    def _add_entered_up_down(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        eu = self.entered_up_var.get_value(time)
        on_up = self.on_up_var.get_value(time)
        on_up_prev = self.on_up_var.get_value(prev_time)
        ed = self.entered_down_var.get_value(time)
        on_down = self.on_down_var.get_value(time)
        on_down_prev = self.on_down_var.get_value(prev_time)
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
        power = self.power_level_var.get_value(time)
        power_prev = self.power_level_var.get_value(prev_time)
        power_step = power - power_prev

        on_up_prev = self.on_up_var.get_value(prev_time)
        on_down_prev = self.on_down_var.get_value(prev_time)
        on_up = self.on_up_var.get_value(time)
        on_down = self.on_down_var.get_value(time)
        aux_up = self.aux_up_grad_var.get_value(time)
        aux_down = self.aux_down_grad_var.get_value(time)
        up_grad = self.up_grad_var.get_value(time)
        down_grad = self.down_grad_var.get_value(time)

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
        dts = self.down_to_stop_grad.get_value(time)
        stop = self.stop_var.get_value(time)
        on_down_prev = self.on_down_var.get_value(prev_time)
        model.add_constraint(dts <= stop, f"down_to_stop_evol_1_{time}_{n}")
        model.add_constraint(dts <= on_down_prev, f"down_to_stop_evol_2_{time}_{n}")
        model.add_constraint(dts >= stop + on_down_prev - 1, f"down_to_stop_evol_3_{time}_{n}")

    def _state_vars(self) -> dict[str, ModelVar]:
        """
        Map each state name used in :attr:`_BANNED_TRANSITIONS` to its :class:`ModelVar`.

        :return: State name to variable
        """
        return {
            "off": self.off_var,
            "on_start": self.on_start_var,
            "on_up": self.on_up_var,
            "on_flat": self.on_flat_var,
            "on_down": self.on_down_var,
            "stop": self.stop_var,
        }

    def _add_mutual_exclusion(self, model: OptimisationModel, time: DateTime) -> None:
        n = self._eq.name
        expr = self.off_var.get_value(time) + self.on_up_var.get_value(time) + self.on_down_var.get_value(time)
        if self._has_flat:
            expr = expr + self.on_flat_var.get_value(time)
        if self._has_stop:
            expr = expr + self.stop_var.get_value(time)
        if self._has_start:
            expr = expr + self.on_start_var.get_value(time)
        model.add_constraint(expr == 1, f"mutual_exclusion_{time}_{n}")

    def _add_initial_boundary_constraints(
        self, model: OptimisationModel, time: DateTime, prev_time: DateTime, ts: Duration
    ) -> None:
        """
        Re-apply the per-step constraints on the step *before* the window.

        A unit with a plateau carries its state one step back from ``start_date``, so the
        transition markers defined there need their defining rows too — otherwise the
        solver is free to set them to anything. Called only when :attr:`has_flat`, and only
        on the first timestep.

        Everything here reads ``prev_time`` and ``prev2``, both outside the window, where
        :class:`ModelVar` serves constants rather than variables. Rows that end up mixing
        two constants are degenerate, not wrong — that is expected on this boundary.

        :param model: The optimisation model
        :param time: First timestep of the window
        :type time: DateTime
        :param prev_time: One step before the window
        :type prev_time: DateTime
        :param ts: Duration of one timestep
        :type ts: Duration
        """
        n = self._eq.name
        prev2 = prev_time - ts  # type: ignore[operator]

        on_flat_prev = self.on_flat_var.get_value(prev_time)
        on_flat_prev2 = self.on_flat_var.get_value(prev2)
        on_up_prev = self.on_up_var.get_value(prev_time)
        on_up_prev2 = self.on_up_var.get_value(prev2)
        on_down_prev = self.on_down_var.get_value(prev_time)
        on_down_prev2 = self.on_down_var.get_value(prev2)
        stable_prev = self.stable_var.get_value(prev_time)
        entered_up_prev = self.entered_up_var.get_value(prev_time)
        entered_down_prev = self.entered_down_var.get_value(prev_time)

        # stable marks the step the unit *enters* the flat state, so it is barred whenever
        # the unit was already flat — same definition as inside the window
        model.add_constraint(stable_prev <= 1 - on_flat_prev2, f"stable_evol_1_{prev_time}_{n}")
        model.add_constraint(stable_prev <= on_flat_prev, f"stable_evol_2_{prev_time}_{n}")
        model.add_constraint(stable_prev >= on_flat_prev - on_flat_prev2, f"stable_evol_3_{prev_time}_{n}")

        model.add_constraint(entered_up_prev <= 1 - on_up_prev2, f"entered_up_evol_1_{prev_time}_{n}")
        model.add_constraint(entered_up_prev <= on_up_prev, f"entered_up_evol_2_{prev_time}_{n}")
        model.add_constraint(entered_up_prev >= on_up_prev - on_up_prev2, f"entered_up_evol_3_{prev_time}_{n}")
        model.add_constraint(entered_down_prev <= 1 - on_down_prev2, f"entered_down_evol_1_{prev_time}_{n}")
        model.add_constraint(entered_down_prev <= on_down_prev, f"entered_down_evol_2_{prev_time}_{n}")
        model.add_constraint(entered_down_prev >= on_down_prev - on_down_prev2, f"entered_down_evol_3_{prev_time}_{n}")

        expr_prev = self.off_var.get_value(prev_time) + on_up_prev + on_down_prev + on_flat_prev
        if self._has_stop:
            expr_prev = expr_prev + self.stop_var.get_value(prev_time)
        if self._has_start:
            expr_prev = expr_prev + self.on_start_var.get_value(prev_time)
        model.add_constraint(expr_prev == 1, f"mutual_exclusion_{prev_time}_{n}")

        # Part of _BANNED_TRANSITIONS one step earlier: the power reversals plus the bans
        # out of STOP. The rest are not re-emitted. Each keeps the number it has inside the
        # window, hence the lookup rather than a count.
        states = self._state_vars()
        bans = self._BANNED_TRANSITIONS[self._has_stop, self._has_start, self._has_flat]
        boundary_bans = [("on_up", "on_down"), ("on_down", "on_up")]
        if self._has_stop:
            boundary_bans += [("stop", "on_flat"), ("stop", "on_down"), ("stop", "on_up")]
        for from_state, to_state in boundary_bans:
            model.add_constraint(
                states[from_state].get_value(prev2) + states[to_state].get_value(prev_time) <= 1,
                f"transition_constraint_{bans.index((from_state, to_state)) + 1}_{prev_time}_{n}",
            )

    def _add_transition_constraints(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        """
        Ban the state changes the unit's machine cannot make — see :attr:`_BANNED_TRANSITIONS`.

        :param model: The optimisation model
        :param time: Current timestep
        :type time: DateTime
        :param prev_time: Previous timestep
        :type prev_time: DateTime
        """
        n = self._eq.name
        states = self._state_vars()
        bans = self._BANNED_TRANSITIONS[self._has_stop, self._has_start, self._has_flat]
        for index, (from_state, to_state) in enumerate(bans, start=1):
            model.add_constraint(
                states[from_state].get_value(prev_time) + states[to_state].get_value(time) <= 1,
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
            stop = self.stop_var.get_value(time)
            evict_stop = time - self._T_stop * ts
            toff_evict = self.turned_off.get_value(evict_stop)
            label = "stop_eviction_constraint" if self._has_start else "eviction_constraint"
            model.add_constraint(toff_evict + stop <= 1, f"{label}_{time}_{n}")
        if self._has_start:
            start = self.on_start_var.get_value(time)
            evict_start = time - self._T_start * ts
            ton_evict = self.turned_on.get_value(evict_start)
            label = "start_eviction_constraint" if self._has_stop else "eviction_constraint"
            model.add_constraint(ton_evict + start <= 1, f"{label}_{time}_{n}")

    def _add_minimum_time_constraints(
        self, model: OptimisationModel, time: DateTime, parameters: AbstractModuleParameters
    ) -> None:
        n = self._eq.name
        ts = parameters.temporal.timestep
        start_date = parameters.temporal.start_date
        start_offset = self._T_start if self._has_start else 0
        stop_offset = self._T_stop if self._has_stop else 0

        on_expr = self.on_up_var.get_value(time) + self.on_down_var.get_value(time)
        if self._has_flat:
            on_expr = on_expr + self.on_flat_var.get_value(time)

        if self._T_on >= 2:
            for steps_back in range(1, self._T_on):
                local_time = time - (steps_back + start_offset) * ts
                model.add_constraint(
                    self.turned_on.get_value(local_time) <= on_expr,
                    f"minimum_time_on_{n}_{local_time}_{time}",
                )
            # the stable phase puts the unit's state one step before the window inside the
            # model, so the minimum-on window anchored on that step has to be enforced too
            if self._has_flat and time == start_date:
                prev_time = time - ts
                on_expr_prev = (
                    self.on_up_var.get_value(prev_time)
                    + self.on_down_var.get_value(prev_time)
                    + self.on_flat_var.get_value(prev_time)
                )
                for steps_back in range(1, self._T_on):
                    local_time = time - (steps_back + start_offset + 1) * ts
                    model.add_constraint(
                        self.turned_on.get_value(local_time) <= on_expr_prev,
                        f"minimum_time_on_{n}_{local_time}_{prev_time}",
                    )

        if self._T_off >= 2:
            for steps_back in range(1, self._T_off):
                local_time = time - (steps_back + stop_offset) * ts
                model.add_constraint(
                    self.turned_off.get_value(local_time) <= self.off_var.get_value(time),
                    f"minimum_time_off_{n}_{local_time}_{time}",
                )

        if self._has_flat and self._T_stable >= 2:
            on_flat = self.on_flat_var.get_value(time)
            for steps_back in range(1, self._T_stable - 1):
                local_time = time - steps_back * ts
                model.add_constraint(
                    self.stable_var.get_value(local_time) <= on_flat,
                    f"minimum_time_stable_{n}_{local_time}_{time}",
                )
            if time == start_date:
                prev_time = time - ts
                on_flat_prev = self.on_flat_var.get_value(prev_time)
                # suffix with prev_time, never `time`: this loop shifts local_time one step
                # further back than the loop above, so reusing `time` collides with the name
                # it already emitted for steps_back + 1. prev_time sits before the window, so it can
                # never clash with a suffix produced at another timestep.
                for steps_back in range(1, self._T_stable - 1):
                    local_time = time - (steps_back + 1) * ts
                    model.add_constraint(
                        self.stable_var.get_value(local_time) <= on_flat_prev,
                        f"minimum_time_stable_{n}_{local_time}_{prev_time}",
                    )

        if self._has_stop and self._T_stop >= 2:
            stop = self.stop_var.get_value(time)
            for steps_back in range(1, self._T_stop - 1):
                local_time = time - steps_back * ts
                model.add_constraint(
                    self.turned_off.get_value(local_time) <= stop,
                    f"shutdown_ramp_{n}_{local_time}_{time}",
                )

        if self._has_start and self._T_start >= 2:
            start = self.on_start_var.get_value(time)
            # naming only; the stray underscore is in the LP references
            prefix = "startup_ramp" if not self._has_flat else "start_up_ramp"
            for steps_back in range(1, self._T_start - 1):
                local_time = time - steps_back * ts
                model.add_constraint(
                    self.turned_on.get_value(local_time) <= start,
                    f"{prefix}_{n}_{local_time}_{time}",
                )

    def _add_power_bounds(self, model: OptimisationModel, time: DateTime) -> None:
        n = self._eq.name
        p = self.power_level_var.get_value(time)
        max_p = self._eq.maximum_power.get_value(time)
        min_p = self._eq.minimum_power.get_value(time)
        q_min = self._eq.minimum_power.max()
        on_up = self.on_up_var.get_value(time)
        on_down = self.on_down_var.get_value(time)
        on_sum = on_up + on_down
        if self._has_flat:
            on_sum = on_sum + self.on_flat_var.get_value(time)

        lb = min_p * on_sum
        ub = max_p * on_sum

        if self._has_stop:
            q_step_down = q_min / self._T_stop
            toff = self.turned_off.get_value(time)
            stop = self.stop_var.get_value(time)
            lb = lb + toff * (q_min - q_step_down)
            ub = ub + stop * q_min - toff * q_step_down

        if self._has_start:
            start = self.on_start_var.get_value(time)
            ub = ub + start * q_min

        model.add_constraint(p >= lb, f"lower_bound_{n}_{time}")
        model.add_constraint(p <= ub, f"upper_bound_{n}_{time}")

    def _add_dd_constraints(self, model: OptimisationModel, time: DateTime, prev_time: DateTime) -> None:
        n = self._eq.name
        swing = self._maximum_power_swing
        stop = self.stop_var.get_value(time)
        dd_prev = self.dd_grad_var.get_value(prev_time)
        d_prev = self.down_grad_var.get_value(prev_time)
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

        p = self.power_level_var.get_value(time)
        p_prev = self.power_level_var.get_value(prev_time)
        power_step = p - p_prev

        ton = self.turned_on.get_value(time)
        toff = self.turned_off.get_value(time)

        if self._has_flat:
            entered_up_prev = self.entered_up_var.get_value(prev_time)
            entered_down_prev = self.entered_down_var.get_value(prev_time)
            u_prev = self.up_grad_var.get_value(prev_time)
            d_prev = self.down_grad_var.get_value(prev_time)
            up_bound = ramp_allowance * entered_up_prev + u_prev + d_prev
            down_bound = -ramp_allowance * entered_down_prev + u_prev + d_prev
        else:
            on_up_prev = self.on_up_var.get_value(prev_time)
            on_down_prev = self.on_down_var.get_value(prev_time)
            up_bound = ramp_allowance * on_up_prev
            down_bound = -ramp_allowance * on_down_prev

        q_min = self._eq.minimum_power.max()

        if self._has_start:
            q_step_up = q_min / self._T_start
            start_prev = self.on_start_var.get_value(prev_time)
            startup_contrib = q_step_up * ton + start_prev * q_step_up
            up_bound = up_bound + startup_contrib
            down_bound = down_bound + startup_contrib
        else:
            up_bound = up_bound + swing * ton

        if self._has_stop:
            q_step_down = q_min / self._T_stop
            stop_prev = self.stop_var.get_value(prev_time)
            shutdown_contrib = -toff * q_step_down - stop_prev * q_step_down
            up_bound = up_bound + shutdown_contrib
            down_bound = down_bound + shutdown_contrib
            if self._has_flat:
                fds = self.flat_down_stop.get_value(time)
                dd_prev = self.dd_grad_var.get_value(prev_time)
                down_bound = down_bound + fds * ramp_allowance - dd_prev
                up_bound = up_bound - dd_prev
            else:
                down_to_stop = self.down_to_stop_grad.get_value(time)
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
