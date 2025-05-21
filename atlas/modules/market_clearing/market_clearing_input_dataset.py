"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import pendulum

from atlas.models.market.market_area import MarketArea
from atlas.models.market.order_coupling import OrderCoupling
from atlas.config import MODEL_TO_NAME_MAPPING
from atlas.models.business_model import BusinessModel
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.modules.market_clearing.market_clearing_data.market_clearing_order import MCOrder
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters


class MarketClearingInputDataset(AbstractDataset[MarketClearingParameters]):
    """Input dataset for Market Clearing module"""

    def __init__(self, raw_data: dict[str, list[BusinessModel]], parameters: MarketClearingParameters):
        self.raw_data = raw_data
        self.parameters = parameters

        step = pendulum.duration(minutes=self.parameters.time_step)
        total_minutes = (self.parameters.end_date - self.parameters.start_date).in_minutes()
        self.times = [self.parameters.start_date + step * i for i in range(0, total_minutes // self.parameters.time_step + 1)]

        self.market_areas: list[MarketArea] = self.get_market_areas(raw_data[MODEL_TO_NAME_MAPPING[MarketArea]])
        self.orders_per_market_area = {}
        self.order_couplings = self.get_order_couplings(raw_data[MODEL_TO_NAME_MAPPING[OrderCoupling]])

    def get_market_areas(self, market_areas: list[MarketArea]) -> list[MarketArea]:
        if self.parameters.market_area_names == "All":
            return market_areas
        else:
            return [
                market_area for market_area in market_areas if market_area.name in self.parameters.market_area_names
            ]

    def get_order_couplings(self, order_couplings: list[OrderCoupling]) -> list[OrderCoupling]:
        return [order_coupling for order_coupling in order_couplings
                if self.is_order_coupling_feasible(order_coupling)
        ]

    def is_order_coupling_feasible(self, order_coupling: OrderCoupling) -> bool:
        order_names = [order.name for order in order_coupling.orders if MCOrder.is_feasible(order, self.times,
                                                                                            self.parameters)]
        if len(order_names) < 2:
            return False
        else:
            return True

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
