"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from enum import IntEnum, StrEnum


class PlanningDelta(IntEnum):
    """Comparison code between the cleared engagement and the new intraday planning for a thermal unit."""

    MODULATION_DOWN = -2  # both plannings above Pmin, new < previous (down-modulate while running)
    SHUTDOWN = -1  # unit was running, new planning shuts it down
    NO_CHANGE = 0
    STARTUP = 1  # unit was off, new planning starts it up
    MODULATION_UP = 2  # both plannings above Pmin, new > previous (up-modulate while running)


class InflexibleChaining(StrEnum):
    """How the inflexible blocks across consecutive timesteps of an order window are coupled."""

    RING = "ring"  # consecutive pairs + last coupled back to first (BRIDGE_UP/DOWN, NEW_START/STOP)
    CHAIN = "chain"  # consecutive pairs only, no closing loop (EXTENDED/SHORTENED)
    NONE = "none"  # no inter-timestep coupling — fully independent orders (MODULATION)


class WindowType(StrEnum):
    """Classification of a thermal order window based on the planning delta and surrounding context."""

    BRIDGE_DOWN = "bridge_down"
    BRIDGE_UP = "bridge_up"
    EXTENDED_BEGINNING = "extended_beginning"
    EXTENDED_END = "extended_end"
    MODULATION_DOWN = "modulation_down"
    MODULATION_UP = "modulation_up"
    NEW_START = "new_start"
    NEW_STOP = "new_stop"
    SHORTENED_BEGINNING = "shortened_beginning"
    SHORTENED_END = "shortened_end"
