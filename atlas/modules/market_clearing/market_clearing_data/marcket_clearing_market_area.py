"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.models.market.market_area import MarketArea
from atlas.modules.market_clearing.market_clearing_data.market_clearing_order import MCOrder


class MCMarketArea:
    def __init__(self, market_area: MarketArea, orders: dict[str, MCOrder]):
        self.market_area = market_area
        self.orders = orders
        self.ref_balance = None # Extract TS
        self.max_price = None # Extract TS
        self.min_price = None # Extract TS
