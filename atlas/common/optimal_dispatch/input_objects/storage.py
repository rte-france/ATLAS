"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.storage import Storage
from atlas.validators import DurationField


class StorageDispatchInput(Storage):
    """
    Physical contract for storage dispatch — fields read by :class:`StorageDispatch`.

    Efficiencies are strictly positive: the dispatch formulation divides by them
    (``power_sell / discharge_efficiency``), and a zero efficiency has no physical
    meaning for a unit that is being dispatched. The base :class:`Storage` object
    allows zero, so the constraint is tightened here rather than there.
    """

    maximum_energy: AbstractTimeseries
    minimum_power: AbstractTimeseries
    maximum_power: AbstractTimeseries
    minimum_state_of_charge: AbstractTimeseries
    charge_efficiency: float = Field(gt=0)
    discharge_efficiency: float = Field(gt=0)
    storage_initial_level: float
    additional_hours: DurationField
