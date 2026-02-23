"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import LazyTimeseries, Solar, Timeseries
from atlas.modules.day_ahead_orders.data_models.portfolio import PortfolioDAO


class SolarDAO(Solar):
    portfolio: PortfolioDAO
    maximum_curtailment_ratio: Timeseries | LazyTimeseries
