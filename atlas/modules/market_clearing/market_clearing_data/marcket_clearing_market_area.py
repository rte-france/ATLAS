"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.models.market.market_area import MarketArea
from atlas.modules.market_clearing.market_clearing_data.market_clearing_order import MCOrder
from atlas.modules.market_clearing.market_clearing_input_dataset import MarketClearingInputDataset


class MCMarketArea:
    def __init__(self, market_area: MarketArea, input_dataset: MarketClearingInputDataset):
        self.market_area = market_area
        self.orders = None
        self.ref_balance = None # Extract TS
        self.max_price = None # Extract TS
        self.min_price = None # Extract TS

    def get_orders(self, input_dataset: MarketClearingInputDataset) -> dict[str, MCOrder]:
        return {
            order_name: mc_order for order_name, mc_order in input_dataset.mc_orders.items()
            if mc_order.order.market_area == self.market_area
        }
