"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.math.timeseries import Timeseries


@dataclass
class ThermalInitialConditions:
    initial_times: list[DateTime]
    stable_initial_times: list[DateTime]
    power_ts: Timeseries | None
    day_zero: bool

    @cached_property
    def extended_start_date(self) -> DateTime:
        return self.initial_times[0]
