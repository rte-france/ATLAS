"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import LazyTimeseries, Load, Timeseries
from atlas.modules.day_ahead_orders.data_models.portfolio import PortfolioDAO


class LoadDAO(Load):
    portfolio: PortfolioDAO
    variable_cost: Timeseries | LazyTimeseries
