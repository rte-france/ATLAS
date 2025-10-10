"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast
from pydantic import BaseModel

from atlas import ControlBlock, CriticalBranch, MarketAreaPtdf, MarketBorder
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.config import INVERSE_MODEL_MAPPING_NAME
from atlas.enum import CouplingType
from atlas.models.business_model import BusinessModel
from atlas.models.market.market_area import MarketArea
from atlas.models.market.order import Order
from atlas.models.market.order_coupling import OrderCoupling
from atlas.modules.market_clearing.market_clearing_parameters import ExchangeConstraintsType, MarketClearingParameters
from atlas.modules.market_clearing.models.control_block_mc import ControlBlockMC
from atlas.modules.market_clearing.models.critical_branch_mc import CriticalBranchMC
from atlas.modules.market_clearing.models.market_area_mc import MarketAreaMC
from atlas.modules.market_clearing.models.market_area_ptdf_mc import MarketAreaPtdfMC
from atlas.modules.market_clearing.models.market_border_mc import MarketBorderMC
from atlas.modules.market_clearing.models.order_coupling_mc import OrderCouplingMC
from atlas.modules.market_clearing.models.order_mc import OrderMC


class MarketClearingInputDataset(AbstractDataset[MarketClearingParameters]):
    """Input dataset for Market Clearing module"""

    def __init__(self, raw_data: dict[str, list[type[BusinessModel]]], parameters: MarketClearingParameters):
        self.raw_data = raw_data
        self.parameters = parameters

        step = self.parameters.time_step
        total_minutes = (self.parameters.end_date - self.parameters.start_date).in_minutes()
        self.times = [
            self.parameters.start_date + step * i
            for i in range(0, total_minutes // int(self.parameters.time_step.total_minutes()))
        ]

        self.is_atc = self.parameters.exchange_constraints_type == ExchangeConstraintsType.ATC

        order_couplings = [cast(OrderCoupling, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[OrderCoupling]]]
        self.mc_order_couplings = self.get_order_couplings(order_couplings)
        orders = [cast(Order, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Order]]]
        self.mc_orders = self.get_orders(orders, self.mc_order_couplings)
        market_areas = [cast(MarketArea, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[MarketArea]]]
        self.mc_market_areas = self.get_market_areas(market_areas, self.mc_orders)
        market_borders = [cast(MarketBorder, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[MarketBorder]]]
        self.mc_market_borders = self.get_market_borders(market_borders)
        control_blocks = [cast(ControlBlock, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[ControlBlock]]]
        self.mc_control_blocks = self.get_control_blocks(control_blocks)

        if self.parameters.exchange_constraints_type == ExchangeConstraintsType.FB:
            critical_branches = [
                cast(CriticalBranch, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[CriticalBranch]]
            ]
            self.mc_critical_branches = self.get_critical_branches(critical_branches)
            market_area_ptdfs = [
                cast(MarketAreaPtdf, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[MarketAreaPtdf]]
            ]
            self.mc_market_area_ptdfs = self.get_market_area_ptdfs(market_area_ptdfs)
        else:
            self.mc_critical_branches = {}
            self.mc_market_area_ptdfs = {}

    def get_critical_branches(self, critical_branches: list[CriticalBranch]) -> dict[str, CriticalBranchMC]:
        if not critical_branches:
            return {}
        mc_critical_branches = {}
        for critical_branch in critical_branches:
            critical_branch_dump = {
                **MarketClearingInputDataset.shallow_dump(critical_branch),
                "time_step": self.parameters.time_step,
                "times": self.times,
            }
            mc_critical_branch = CriticalBranchMC.model_validate(critical_branch_dump)
            mc_critical_branches[critical_branch.name] = mc_critical_branch
        return mc_critical_branches

    def get_control_blocks(self, control_blocks: list[ControlBlock]) -> dict[str, ControlBlockMC]:
        control_blocks_to_keep = {}
        for control_block in control_blocks:
            for mc_market_area in self.mc_market_areas.values():
                if control_block == mc_market_area.control_block:
                    control_block_dump = MarketClearingInputDataset.shallow_dump(control_block)
                    mc_control_block = ControlBlockMC.model_validate(control_block_dump)
                    control_blocks_to_keep[control_block.name] = mc_control_block
        return control_blocks_to_keep

    def get_market_areas(
        self, market_areas: list[MarketArea], mc_orders: dict[str, OrderMC]
    ) -> dict[str, MarketAreaMC]:
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
                if mc_order.market_area.name == market_area.name
            }
            market_area_dump = {
                **MarketClearingInputDataset.shallow_dump(market_area),
                "time_step": self.parameters.time_step,
                "times": self.times,
                "mc_orders": market_area_orders,
            }
            mc_market_area = MarketAreaMC.model_validate(market_area_dump)
            mc_market_areas[market_area.name] = mc_market_area

        return mc_market_areas

    def get_orders(self, orders: list[Order], order_couplings: dict[str, OrderCouplingMC]) -> dict[str, OrderMC]:
        mc_orders = {}
        for order in orders:
            if OrderMC.is_feasible(order, self.times, self.parameters):
                id_with_status = True if order.qmin and order.qmin > self.parameters.allowed_round_off_error else False
                order_dump = {
                    **MarketClearingInputDataset.shallow_dump(order),
                    "time_step": self.parameters.time_step,
                    "id_with_status": id_with_status
                }
                mc_order = OrderMC.model_validate(order_dump)
                mc_orders[order.name] = mc_order

        for order_coupling in order_couplings.values():
            for order in order_coupling.orders:
                if order.name not in mc_orders:
                    continue
                mc_order = mc_orders[order.name]
                if order_coupling.coupling_type == CouplingType.EXCLUSION:
                    mc_order.id_with_status = True
                    mc_order.is_mutually_excluding = True
                if order_coupling.coupling_type == CouplingType.IDENTICAL_VOLUME:
                    mc_order.is_linked = True
                    mc_order.link_id = order_coupling.name
                if order_coupling.coupling_type == CouplingType.IDENTICAL_RATIO:
                    mc_order.is_linked = True
                    mc_order.link_id = order_coupling.name
                # Uncomment to enforce the PC constraint
                if order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                    mc_order.is_parent_children = True
                    mc_order.id_with_status = True
                    mc_order.parent_child_id = order_coupling.name
                if order_coupling.coupling_type == CouplingType.COMPLEMENT:
                    mc_order.is_linked = True
                    mc_order.link_id = order_coupling.name
            if order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                if len(order_coupling.orders) > 0:
                    order = order_coupling.orders[0]
                    mc_orders[order.name].is_parent = True
                    if mc_orders[order.name].order_coupling_parent_ids is None:
                        mc_orders[order.name].order_coupling_parent_ids = [order_coupling.name]
                    else:
                        mc_orders[order.name].order_coupling_parent_ids.append(order_coupling.name)

        return mc_orders

    def get_order_couplings(self, order_couplings: list[OrderCoupling]) -> dict[str, OrderCouplingMC]:
        mc_order_couplings = {}
        for order_coupling in order_couplings:
            if self.is_order_coupling_feasible(order_coupling):
                order_coupling_dump = MarketClearingInputDataset.shallow_dump(order_coupling)
                mc_order_coupling = OrderCouplingMC.model_validate(order_coupling_dump)
                mc_order_couplings[order_coupling.name] = mc_order_coupling
        return mc_order_couplings

    def is_order_coupling_feasible(self, order_coupling: OrderCoupling) -> bool:
        if order_coupling.orders is None:
            return False
        order_names = [
            order.name for order in order_coupling.orders if OrderMC.is_feasible(order, self.times, self.parameters)
        ]
        if len(order_names) < 2:
            return False
        else:
            return True

    def get_market_borders(self, market_borders: list[MarketBorder]) -> dict[str, MarketBorderMC]:
        mc_market_borders = {}
        for market_border in market_borders:
            market_border_dump = {
                **MarketClearingInputDataset.shallow_dump(market_border),
                "time_step": self.parameters.time_step,
                "times": self.times,
            }
            mc_market_border = MarketBorderMC.model_validate(market_border_dump)
            mc_market_borders[market_border.name] = mc_market_border
        return mc_market_borders

    def get_market_area_ptdfs(self, market_area_ptdfs: list[MarketAreaPtdf]) -> dict[str, MarketAreaPtdfMC]:
        mc_market_area_ptdfs = {}
        for market_area_ptdf in market_area_ptdfs:
            market_area_ptdf_dump = {
                **MarketClearingInputDataset.shallow_dump(market_area_ptdf),
                "time_step": self.parameters.time_step,
                "times": self.times,
            }
            mc_market_area_ptdf = MarketAreaPtdfMC.model_validate(market_area_ptdf_dump)
            mc_market_area_ptdfs[market_area_ptdf.name] = mc_market_area_ptdf
        return mc_market_area_ptdfs

    @staticmethod
    def shallow_dump(model: BaseModel) -> dict:
        result = {}
        for name, value in model.__dict__.items():
            # Si c’est une liste de BaseModel, on ne touche pas
            if isinstance(value, list) and all(isinstance(v, BaseModel) for v in value):
                result[name] = value
            # Si c’est un BaseModel, on ne touche pas non plus
            elif isinstance(value, BaseModel):
                result[name] = value
            else:
                result[name] = value
        return result

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
