"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas import MarketBorder, ControlBlock, CriticalBranch
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.config import INVERSE_MODEL_MAPPING_NAME
from atlas.models.business_model import BusinessModel
from atlas.models.market.market_area import MarketArea
from atlas.models.market.order import Order
from atlas.models.market.order_coupling import OrderCoupling
from atlas.modules.market_clearing.market_clearing_data.marcket_clearing_market_area import MCMarketArea
from atlas.modules.market_clearing.market_clearing_data.market_clearing_border import MCBorder
from atlas.modules.market_clearing.market_clearing_data.market_clearing_critical_branch import MCCriticalBranch
from atlas.modules.market_clearing.market_clearing_data.market_clearing_order import MCOrder
from atlas.modules.market_clearing.market_clearing_parameters import MarketClearingParameters, ExchangeConstraintsType


class MarketClearingInputDataset(AbstractDataset[MarketClearingParameters]):
    """Input dataset for Market Clearing module"""

    def __init__(self, raw_data: dict[str, list[BusinessModel]], parameters: MarketClearingParameters):
        self.raw_data = raw_data
        self.parameters = parameters

        step = pendulum.duration(minutes=self.parameters.time_step)
        total_minutes = (self.parameters.end_date - self.parameters.start_date).in_minutes()
        self.times = [
            self.parameters.start_date + step * i for i in range(0, total_minutes // self.parameters.time_step)
        ]

        self.order_couplings = self.get_order_couplings(raw_data[INVERSE_MODEL_MAPPING_NAME[OrderCoupling]])
        self.mc_orders = self.get_orders(raw_data[INVERSE_MODEL_MAPPING_NAME[Order]], self.order_couplings)
        self.mc_market_areas = self.get_market_areas(raw_data[INVERSE_MODEL_MAPPING_NAME[MarketArea]], self.mc_orders)
        self.mc_market_borders = self.get_market_borders(raw_data[INVERSE_MODEL_MAPPING_NAME[MarketBorder]])
        self.control_blocks = self.get_control_blocks(raw_data[INVERSE_MODEL_MAPPING_NAME[ControlBlock]])
        if self.parameters.exchange_constraints_type == ExchangeConstraintsType.FB:
            if INVERSE_MODEL_MAPPING_NAME[CriticalBranch] in raw_data:
                self.mc_critical_branches = self.get_critical_branches(raw_data[INVERSE_MODEL_MAPPING_NAME[CriticalBranch]])
            else:
                self.mc_critical_branches = {}
        else:
            self.mc_critical_branches = None

    def get_critical_branches(self, critical_branches: list[CriticalBranch]) -> dict[str, MCCriticalBranch]:
        return {critical_branche.name: MCCriticalBranch(critical_branche, self.times, self.parameters.time_step) for critical_branche in critical_branches}

    def get_control_blocks(self, control_blocks: list[ControlBlock]) -> dict[str, ControlBlock]:
        control_blocks_to_keep = {}
        for control_block in control_blocks:
            for mc_market_area in self.mc_market_areas.values():
                if control_block == mc_market_area.market_area.control_block:
                    control_blocks_to_keep[control_block.name] = control_block
        return control_blocks_to_keep

    def get_market_areas(
        self, market_areas: list[MarketArea], mc_orders: dict[str, MCOrder]
    ) -> dict[str, MCMarketArea]:
        if self.parameters.market_area_names == "All":
            market_areas_to_keep = market_areas
        else:
            market_areas_to_keep = [
                market_area for market_area in market_areas if market_area.name in self.parameters.market_area_names
            ]
        mc_market_areas = {}
        for market_area in market_areas_to_keep:
            market_area_orders = {
                order_name: mc_order
                for order_name, mc_order in mc_orders.items()
                if mc_order.order.market_area == market_area
            }
            mc_market_areas[market_area.name] = MCMarketArea(market_area, market_area_orders, self.times, self.parameters.time_step)
        return mc_market_areas

    def get_orders(self, mc_orders: list[Order], order_couplings: dict[str:OrderCoupling]) -> dict[str, MCOrder]:
        mc_orders = {
            order.name: MCOrder(order, self.parameters)
            for order in mc_orders
            if MCOrder.is_feasible(order, self.times, self.parameters)
        }
        for order_coupling in order_couplings.values():
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

    def get_order_couplings(self, order_couplings: list[OrderCoupling]) -> dict[str:OrderCoupling]:
        return {
            order_coupling.name: order_coupling
            for order_coupling in order_couplings
            if self.is_order_coupling_feasible(order_coupling)
        }

    def is_order_coupling_feasible(self, order_coupling: OrderCoupling) -> bool:
        if order_coupling.orders is None:
            return False
        order_names = [
            order.name for order in order_coupling.orders if MCOrder.is_feasible(order, self.times, self.parameters)
        ]
        if len(order_names) < 2:
            return False
        else:
            return True

    def get_market_borders(self, market_borders: list[MarketBorder]) -> dict[str, MCBorder]:
        return {market_border.name: MCBorder(market_border, self.times, self.parameters.time_step) for market_border in market_borders}

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
