"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import Duration

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.thermal import Thermal


class ThermalDispatchInput(Thermal):
    """
    Physical contract for thermal dispatch — fields read by :class:`ThermalDispatch`.
    """

    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    minimum_time_on: Duration
    minimum_time_off: Duration
    minimum_stable_power_duration: Duration
