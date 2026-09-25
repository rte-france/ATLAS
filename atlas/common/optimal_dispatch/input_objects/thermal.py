"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.thermal import Thermal
from atlas.validators import DurationField


class ThermalDispatchInput(Thermal):
    """
    Physical contract for thermal dispatch — fields read by :class:`ThermalDispatch`.
    """

    maximum_power: AbstractTimeseries
    minimum_power: AbstractTimeseries
    minimum_time_on: DurationField
    minimum_time_off: DurationField
    minimum_stable_power_duration: DurationField
