"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock


class ControlBlockPO(ControlBlock):
    positive_imbalance_price: Timeseries | LazyTimeseries
    negative_imbalance_price: Timeseries | LazyTimeseries
