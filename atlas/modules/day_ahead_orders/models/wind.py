"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import LazyTimeseries, Timeseries, Wind
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO


class WindDAO(Wind):
    portfolio: PortfolioDAO
    maximum_curtailment_ratio: Timeseries | LazyTimeseries
