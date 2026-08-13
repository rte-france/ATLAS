"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

State-sequence builders. A state sequence encodes the operating regime of a thermal unit
over a time frame, using :class:`~atlas.enums.ThermalOrderState` values.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import polars as pl

import atlas.config as cfg
from atlas.enums import ThermalDispatchState, ThermalOrderState, ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.timing import generate_datetimes

if TYPE_CHECKING:
    from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
    from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
    from atlas.modules.day_ahead_orders.steps.thermal.dispatch.optimization_step import ThermalOptimisationResult


def build_baseload_state_sequence(
    unit: ThermalDAO,
    parameters: DayAheadOrdersParameters,
) -> tuple[Timeseries, bool]:
    """
    Compute the operating-state sequence of a baseload unit over an extended time frame.

    The extended frame is ``start_date - T_traceback * step ... end_date + T_traceback * step``
    where ``T_traceback`` is large enough to cover any straddling startup or shutdown ramp.

    State encoding (see :class:`~atlas.enums.ThermalOrderState`):
    OFF = 0, ON = 1, STARTUP = 2, SHUTDOWN = 3.

    A sequence is flagged ``inconsistent`` and aborted if more than one startup or one
    shutdown is detected, if startup/shutdown ramps overlap, or if the gap between
    ramps violates ``minimum_time_on``/``minimum_time_off``.

    :return: ``(states_sequence, inconsistent)`` — when ``inconsistent`` is ``True``, the
        returned sequence may be partially built and should not be used.
    """
    if unit.strategy != ThermalStrategy.BASE:
        cfg.logger.error(f"Equipement {unit.name} is not of strategy 'Base'.")
        raise ValueError("Wrong equipment type for the thermic optimization program.")

    step = parameters.temporal.timestep
    T_on = int(max(1, math.ceil(unit.minimum_time_on / step)))
    T_off = int(max(1, math.ceil(unit.minimum_time_off / step)))
    T_start = int(math.floor(unit.startup_duration / step))
    T_stop = int(math.floor(unit.shutdown_duration / step))
    maximum_power = unit.maximum_power

    T_traceback = int(max(T_on + T_start, T_off + T_stop)) + 1
    extended_start = parameters.temporal.start_date - T_traceback * step
    extended_end = parameters.temporal.end_date + T_traceback * step
    extended_time_frame = generate_datetimes(extended_start, extended_end, step)

    states_sequence = Timeseries.from_index(
        start_date=extended_start, frequency=step, end_date=extended_end, default_value=0
    )

    for t in extended_time_frame:
        if maximum_power is not None and t in maximum_power and maximum_power.get_value(t) > 0:
            if t in states_sequence:
                states_sequence.set_value(t, ThermalOrderState.ON)
            else:
                states_sequence.add_index(t, ThermalOrderState.ON)

    # Count startups/shutdowns over the extended frame. More than one of either → inconsistent.
    startup_count, shutdown_count = 0, 0
    for t in extended_time_frame[1:]:
        t_prev = t - step
        if states_sequence.get_value(t) - states_sequence.get_value(t_prev) == ThermalOrderState.ON:
            startup_count += 1
        elif states_sequence.get_value(t_prev) - states_sequence.get_value(t) == ThermalOrderState.ON:
            shutdown_count += 1

    if startup_count > 1 or shutdown_count > 1:
        return states_sequence, True

    # Reconstruct startup and shutdown ramp windows (only when relevant).
    if T_start > 0 or T_stop > 0:
        started_at_t: object = None
        end_of_start_up: object = None
        startup_time_frame: list = []
        for t in extended_time_frame[1:]:
            t_prev = t - step
            if states_sequence.get_value(t) - states_sequence.get_value(t_prev) == ThermalOrderState.ON:
                started_at_t = t
                end_of_start_up = started_at_t + T_start * step
                startup_time_frame = generate_datetimes(started_at_t, end_of_start_up - step, step)
                break

        stopped_at_t: object = None
        end_of_shutdown: object = None
        shutdown_time_frame: list = []
        for t in extended_time_frame[1:]:
            t_prev = t - step
            if states_sequence.get_value(t_prev) - states_sequence.get_value(t) == ThermalOrderState.ON:
                end_of_shutdown = t
                stopped_at_t = end_of_shutdown - T_stop * step
                shutdown_time_frame = generate_datetimes(stopped_at_t, end_of_shutdown - step, step)
                break

        if startup_time_frame and shutdown_time_frame:
            if set(startup_time_frame) & set(shutdown_time_frame):
                return states_sequence, True
            # Spacing rule between ramps: enforce T_on (ramps in startup-then-shutdown order)
            # or T_off (shutdown-then-startup order).
            if (end_of_shutdown - started_at_t).total_minutes() >= 0 and int(  # type: ignore[operator]
                math.floor((stopped_at_t - end_of_start_up) / step)  # type: ignore[operator]
            ) < T_on:
                return states_sequence, True
            if (end_of_shutdown - started_at_t).total_minutes() < 0 and int(  # type: ignore[operator]
                math.floor((started_at_t - end_of_shutdown) / step)  # type: ignore[operator]
            ) < T_off:
                return states_sequence, True

        for t in startup_time_frame:
            if t in states_sequence:
                states_sequence.set_value(t, ThermalOrderState.STARTUP)
            else:
                states_sequence.add_index(t, ThermalOrderState.STARTUP)
        for t in shutdown_time_frame:
            if t in states_sequence:
                states_sequence.set_value(t, ThermalOrderState.SHUTDOWN)
            else:
                states_sequence.add_index(t, ThermalOrderState.SHUTDOWN)

    return states_sequence, False


def build_intermediate_state_sequence(res: ThermalOptimisationResult) -> Timeseries:
    """
    Compute the operating-state sequence of an intermediate unit from a solved LP result.

    Uses :class:`~atlas.enums.ThermalOrderState` encoding. The presence of ``start``,
    ``stop`` and ``on_flat`` in the LP result determines which ramp phases are active —
    no unit parameters needed.
    """
    states_sequence = res.off * ThermalOrderState.OFF + res.on_up + res.on_down

    if res.on_flat is not None:
        states_sequence += res.on_flat
    if res.start is not None:
        states_sequence += res.start * ThermalOrderState.STARTUP
    if res.stop is not None:
        states_sequence += res.stop * ThermalOrderState.SHUTDOWN

    return states_sequence


def build_dispatch_state_sequence(
    res: ThermalOptimisationResult,
    parameters: DayAheadOrdersParameters,
) -> Timeseries:
    """
    Compute the detailed dispatch-state sequence of an intermediate unit from a solved LP result.

    Uses :class:`~atlas.enums.ThermalDispatchState` (distinguishes ON_UP, ON_DOWN, ON_FLAT, etc.)
    and is stored on the unit for downstream modules to consume.
    """
    tz = parameters.temporal.start_date.timezone_name
    local_time_index = list(res.off.index)

    values: list[float] = []
    for time in local_time_index:
        if res.on_up.get_value(time) == 1:
            values.append(ThermalDispatchState.ON_UP)
            continue
        if res.on_down.get_value(time) == 1:
            values.append(ThermalDispatchState.ON_DOWN)
            continue
        if res.off.get_value(time) == 1:
            values.append(ThermalDispatchState.OFF)
            continue
        if res.start is not None and res.start.get_value(time) == 1:
            values.append(ThermalDispatchState.START)
            continue
        if res.stop is not None and res.stop.get_value(time) == 1:
            values.append(ThermalDispatchState.STOP)
            continue
        if res.on_flat is not None and res.on_flat.get_value(time) == 1:
            values.append(ThermalDispatchState.ON_FLAT)
            continue
        values.append(ThermalDispatchState.UNKNOWN)

    return Timeseries(
        pl.DataFrame(
            {"time": local_time_index, "value": values},
            schema={"time": pl.Datetime("us", tz), "value": pl.Float64()},
        )
    )
