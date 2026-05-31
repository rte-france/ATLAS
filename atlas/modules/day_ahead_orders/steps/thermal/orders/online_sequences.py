"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pendulum

if TYPE_CHECKING:
    from pendulum import DateTime, Duration

    from atlas.math.timeseries import Timeseries


def extract_online_sequences(
    states_sequence: Timeseries,
    orders_time: list[DateTime],
    timestep: Duration,
    case: str = "",
) -> list[tuple[Timeseries, str]]:
    """
    Extract one or more contiguous online sub-windows from a thermal unit's state sequence.

    A unit may restart over the order window, producing multiple online intervals separated
    by offline gaps. This function detects those gaps (any inter-step delta greater than
    ``timestep``) and slices the state sequence accordingly.

    :param states_sequence: A state-encoded timeseries (``ThermalOrderState`` values).
    :param orders_time: Reference ordered list of timesteps.
    :param timestep: Simulation timestep duration.
    :param case: Optional price scenario name carried along with each sub-window.
    :return: List of ``(sub_window_timeseries, case)`` tuples (empty if the unit is offline throughout).
    """
    online_at_t = sorted([pendulum.instance(dt) for dt in set(orders_time).intersection(states_sequence.index)])

    # Build sequence of interval boundaries: each gap > timestep produces a pair of bounds.
    intervals: list[DateTime] = []
    if online_at_t:
        intervals.append(online_at_t[0])
        if len(online_at_t) >= 2:
            for i in range(len(online_at_t) - 1):
                if not (online_at_t[i + 1] - online_at_t[i]) == timestep:
                    intervals.append(online_at_t[i])
                    intervals.append(online_at_t[i + 1])
        intervals.append(online_at_t[-1])

    sub_windows: list[tuple[Timeseries, str]] = []
    if intervals:
        intervals.sort()
        for i in range(int(len(intervals) / 2)):
            window = states_sequence.slice(intervals[2 * i], intervals[2 * i + 1], "both", False)
            # Deduplicate identical windows (can happen on singleton intervals).
            if len(sub_windows) == 0:
                sub_windows.append((window, case))
            elif all(window != ts for ts, _ in sub_windows):
                sub_windows.append((window, case))

    return sub_windows
