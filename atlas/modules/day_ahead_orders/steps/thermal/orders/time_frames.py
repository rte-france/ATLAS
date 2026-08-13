"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from atlas.enums import ThermalOrderState
from atlas.timing import generate_datetimes

if TYPE_CHECKING:
    from pendulum import DateTime, Duration

    from atlas.math.timeseries import Timeseries


@dataclass
class ThermalTimeFrames:
    """
    Time frame partitions derived from a thermal unit's state sequence.

    :param flexible: Timesteps where the unit is in stable ON state, used for flexible and reserve orders.
    :param startup: Timesteps covering the startup ramp window (one step longer than the ramp, clipped to the sim window).
    :param shutdown: Timesteps covering the shutdown ramp window (shifted back one step, null-power step excluded).
    :param inflexible: All online timesteps, used for inflexible (Pmin) orders.
    :param K_start: Number of STARTUP-state timesteps within the simulation window.
    :param K_stop: Number of SHUTDOWN-state timesteps within the simulation window.
    :param startup_ends_here: True when the startup ramp completes within the simulation window (STARTUP→ON transition visible).
    :param shutdown_starts_here: True when the shutdown ramp begins within the simulation window (ON→SHUTDOWN transition visible).
    """

    flexible: list[DateTime]
    startup: list[DateTime]
    shutdown: list[DateTime]
    inflexible: list[datetime]
    K_start: int
    K_stop: int
    startup_ends_here: bool
    shutdown_starts_here: bool


def compute_time_frames(
    online_timeframe: Timeseries,
    orders_time: list[DateTime],
    step: Duration,
) -> ThermalTimeFrames:
    """
    Partition the simulation window into flexible, startup, shutdown and inflexible time frames.

    :param online_timeframe: State-encoded timeseries (:class:`~atlas.enums.ThermalOrderState` values).
    :param orders_time: Ordered list of simulation timesteps.
    :param step: Simulation timestep duration.
    :return: Populated :class:`ThermalTimeFrames`.
    """
    online_values = online_timeframe.values
    online_index = online_timeframe.index

    # Detect startup completion (STARTUP→ON) and shutdown initiation (ON→SHUTDOWN)
    startup_ends_here = False
    shutdown_starts_here = False
    _startup_to_on = ThermalOrderState.STARTUP - ThermalOrderState.ON
    _on_to_shutdown = ThermalOrderState.SHUTDOWN - ThermalOrderState.ON
    for a, b in zip(online_values[:-1], online_values[1:], strict=False):
        if b - a == _on_to_shutdown:
            shutdown_starts_here = True
        if a - b == _startup_to_on:
            startup_ends_here = True
        if startup_ends_here and shutdown_starts_here:
            break

    # Count ramp timesteps and locate the first ramp timestep within the window
    online_index_set = set(online_index)
    orders_time_set = set(orders_time)
    K_start = K_stop = 0
    begin_startup: DateTime | None = None
    begin_shutdown: DateTime | None = None
    flexible: list[DateTime] = []

    for t in orders_time:
        if t not in online_index_set:
            continue
        v = online_timeframe.get_value(t)
        if v == ThermalOrderState.ON:
            flexible.append(t)
        elif v == ThermalOrderState.STARTUP:
            K_start += 1
            if begin_startup is None:
                begin_startup = t
        elif v == ThermalOrderState.SHUTDOWN:
            K_stop += 1
            if begin_shutdown is None:
                begin_shutdown = t

    # Startup ramp window: one step longer than K_start, clipped to sim window
    startup: list[DateTime] = []
    startup_set: set[DateTime] = set()
    if K_start > 0:
        assert begin_startup is not None
        startup = [
            t for t in generate_datetimes(begin_startup, begin_startup + K_start * step, step) if t in orders_time_set
        ]
        startup_set = set(startup)

    # Shutdown ramp window: shifted back one step (last stable Pmin step included), last null-power step excluded
    shutdown: list[DateTime] = []
    shutdown_set: set[DateTime] = set()
    if K_stop > 0:
        assert begin_shutdown is not None
        shutdown = [
            t
            for t in generate_datetimes(begin_shutdown - step, begin_shutdown + (K_stop - 1) * step, step)
            if t in orders_time_set
        ]
        shutdown_set = set(shutdown)

    # Remove startup/shutdown overlaps from flexible (boundary Pmin steps belong to ramp windows)
    if startup_set or shutdown_set:
        flexible = [t for t in flexible if t not in startup_set and t not in shutdown_set]

    # Corner case: unit online for exactly one step → singleton overlap → drop from shutdown
    if K_start > 0 and K_stop > 0:
        overlap = startup_set & shutdown_set
        if len(overlap) == 1:
            shutdown = [t for t in shutdown if t not in overlap]

    return ThermalTimeFrames(
        flexible=flexible,
        startup=startup,
        shutdown=shutdown,
        inflexible=online_index,
        K_start=K_start,
        K_stop=K_stop,
        startup_ends_here=startup_ends_here,
        shutdown_starts_here=shutdown_starts_here,
    )
