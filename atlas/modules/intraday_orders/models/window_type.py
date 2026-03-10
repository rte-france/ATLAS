"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from enum import Enum


class WindowType(str, Enum):
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
