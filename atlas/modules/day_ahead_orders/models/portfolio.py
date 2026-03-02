"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import Portfolio
from atlas.modules.day_ahead_orders.models.market_area import MarketAreaDAO


class PortfolioDAO(Portfolio):
    market_area: MarketAreaDAO
