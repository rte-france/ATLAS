"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from dataclasses import dataclass, field

from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.steps.result import EquipmentOptimisationResult


@dataclass
class ThermalOptimisationResult(EquipmentOptimisationResult):
    """
    Direct LP solver output for a thermal unit — variable values extracted after solve().

    Required fields correspond to variables present in every LP solve.
    Optional fields (``start``, ``stop``, ``on_flat``) are only set when the
    corresponding time parameters (T_start, T_stop, T_stable) are non-zero.

    :param power_output: Power output per timestep in MW.
    :param contracted_difference_up: Upward manual reserve shortfall.
    :param contracted_difference_down: Downward manual reserve shortfall.
    :param automated_contracted_difference_up: Upward automated reserve shortfall.
    :param automated_contracted_difference_down: Downward automated reserve shortfall.
    :param on_up: Binary — unit is ON and ramping up.
    :param on_down: Binary — unit is ON and ramping down.
    :param off: Binary — unit is OFF.
    :param start: Binary — unit is in start-up phase (None if T_start == 0).
    :param stop: Binary — unit is in shutdown phase (None if T_stop == 0).
    :param on_flat: Binary — unit is ON at stable power (None if T_stable == 0).
    """

    power_output: Timeseries = field(default_factory=Timeseries)
    contracted_difference_up: Timeseries = field(default_factory=Timeseries)
    contracted_difference_down: Timeseries = field(default_factory=Timeseries)
    automated_contracted_difference_up: Timeseries = field(default_factory=Timeseries)
    automated_contracted_difference_down: Timeseries = field(default_factory=Timeseries)
    on_up: Timeseries = field(default_factory=Timeseries)
    on_down: Timeseries = field(default_factory=Timeseries)
    off: Timeseries = field(default_factory=Timeseries)
    start: Timeseries | None = None
    stop: Timeseries | None = None
    on_flat: Timeseries | None = None
