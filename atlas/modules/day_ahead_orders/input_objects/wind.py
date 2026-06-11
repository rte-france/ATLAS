"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.objects.equipment.wind import Wind


class WindDAO(Wind):
    maximum_curtailment_ratio: AbstractTimeseries
