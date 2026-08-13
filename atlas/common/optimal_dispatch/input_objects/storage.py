"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.storage import Storage
from atlas.validators import DurationField


class StorageDispatchInput(Storage):
    """
    Physical contract for storage dispatch — fields read by :class:`StorageDispatch`.
    """

    maximum_energy: AbstractTimeseries
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    minimum_state_of_charge: AbstractTimeseries
    charge_efficiency: float
    discharge_efficiency: float
    storage_initial_level: float
    additional_hours: DurationField
