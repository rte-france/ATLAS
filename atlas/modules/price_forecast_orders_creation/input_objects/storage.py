"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import AbstractTimeseries, Storage
from atlas.objects.equipment.equipment import AdditionalHours


class StoragePFOC(Storage):
    charge_efficiency: float
    discharge_efficiency: float
    antares_dispatch: AbstractTimeseries
    variable_cost: AbstractTimeseries
    additional_hours: AdditionalHours
