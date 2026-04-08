"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.models.market.market_area import MarketArea
from atlas.models.market_operator.portfolio import Portfolio


class PortfolioDAO(Portfolio):
    market_area: MarketArea
