"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
import pendulum

from atlas.models.market.order import Order
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

        self.market_areas = self.get_market_areas(raw_data[MODEL_TO_NAME_MAPPING[MarketArea]])
        self.order_couplings = self.get_order_couplings(raw_data[MODEL_TO_NAME_MAPPING[OrderCoupling]])
        self.mc_orders = self.get_orders(raw_data[MODEL_TO_NAME_MAPPING[Order]])
        self.orders_per_market_area = self.get_orders_per_market_area()

    def get_market_areas(self, market_areas: list[MarketArea]) -> dict[str, MarketArea]:
        if self.parameters.market_area_names == "All":
            return {market_area.name: market_area for market_area in market_areas}
        else:
            return {
                market_area.name: market_area for market_area in market_areas if market_area.name in self.parameters.market_area_names
            }

    def get_orders(self, mc_orders: list[Order], order_couplings: list[OrderCoupling]) -> dict[str, MCOrder]:
        mc_orders = {order.name: MCOrder(order) for order in mc_orders if MCOrder.is_feasible(order, self.times, self.parameters)}
        for order_coupling in order_couplings:
            for order in order_coupling.orders:
                if order.name not in mc_orders:
                    continue
                mc_order = mc_orders[order.name]
                if order_coupling.coupling_type == "EXCLUSION":
                    mc_order.id_with_status = True
                    mc_order.is_mutually_excluding = True
                if order_coupling.coupling_type == "IDENTICAL_VOLUME":
                    mc_order.is_linked = True
                    mc_order.link_id = order_coupling.name
                if order_coupling.coupling_type == "IDENTICAL_RATIO":
                    mc_order.is_linked = True
                    mc_order.link_id = order_coupling.name
                # Uncomment to enforce the PC constraint
                if order_coupling.coupling_type == "PARENT_CHILDREN":
                    mc_order.is_parent_children = True
                    mc_order.id_with_status = True
                    mc_order.parent_child_id = order_coupling.name
                if order_coupling.coupling_type == "COMPLEMENT":
                    mc_order.is_linked = True
                    mc_order.link_id = order_coupling.name
        return mc_orders

    def get_order_couplings(self, order_couplings: list[OrderCoupling]) -> dict[str: OrderCoupling]:
        return {order_coupling.name: order_coupling for order_coupling in order_couplings
                if self.is_order_coupling_feasible(order_coupling)
                }
    def get_orders_per_market_area(self):
        return{
            {
                order_name: mc_order for order_name, mc_order in self.mc_orders.items() if mc_order.order.market_area == market_area
            } for market_area in self.market_areas.values()
         }

    def is_order_coupling_feasible(self, order_coupling: OrderCoupling) -> bool:
        order_names = [order.name for order in order_coupling.orders if MCOrder.is_feasible(order, self.times,
                                                                                            self.parameters)]
        if len(order_names) < 2:
            return False
        else:
            return True

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
