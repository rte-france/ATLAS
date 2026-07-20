"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

import pendulum

from atlas.abstract_class.dataset import AbstractDataset
from atlas.enums import CouplingType
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.market_clearing.input_objects.critical_branch import CriticalBranchMC
from atlas.modules.market_clearing.input_objects.market_area import MarketAreaMC
from atlas.modules.market_clearing.input_objects.market_area_ptdf import MarketAreaPtdfMC
from atlas.modules.market_clearing.input_objects.market_border import MarketBorderMC
from atlas.modules.market_clearing.input_objects.order import OrderMC
from atlas.modules.market_clearing.input_objects.order_coupling import OrderCouplingMC
from atlas.modules.market_clearing.parameters import ExchangeConstraintsType, MarketClearingParameters
from atlas.objects.market.critical_branch import CriticalBranch
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market.market_area_ptdf import MarketAreaPtdf
from atlas.objects.market.market_border import MarketBorder
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling
from atlas.objects.network_operator.control_block import ControlBlock
from atlas.timing import generate_datetimes

# IDENTICAL_VOLUME, IDENTICAL_RATIO and COMPLEMENT couplings all link their orders' surplus the
# same way in Pricing; only EXCLUSION and PARENT_CHILDREN set distinct flags.
_LINKING_COUPLING_TYPES = (CouplingType.IDENTICAL_VOLUME, CouplingType.IDENTICAL_RATIO, CouplingType.COMPLEMENT)


def _apply_coupling_flags(mc_order: OrderMC, order_coupling: OrderCouplingMC) -> None:
    if order_coupling.coupling_type == CouplingType.EXCLUSION:
        mc_order.requires_status_variable = True
        mc_order.is_mutually_excluding = True
    elif order_coupling.coupling_type in _LINKING_COUPLING_TYPES:
        mc_order.is_linked = True
        mc_order.link_id = order_coupling.name
    elif order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
        mc_order.is_in_parent_child_coupling = True
        mc_order.requires_status_variable = True
        mc_order.parent_child_id = order_coupling.name


class MarketClearingInputDataset(AbstractDataset[MarketClearingParameters]):
    """Input dataset for Market Clearing module"""

    def __init__(self, input_data: AtlasDataset, parameters: MarketClearingParameters):
        self.input_data = input_data
        self.parameters = parameters
        self.times = generate_datetimes(
            self.parameters.temporal.start_date,
            cast(pendulum.DateTime, self.parameters.temporal.end_date - self.parameters.temporal.timestep),
            self.parameters.temporal.timestep,
        )

        self.is_atc = self.parameters.exchange_constraints_type == ExchangeConstraintsType.ATC

        order_couplings = [cast(OrderCoupling, obj) for obj in input_data.order_coupling]
        self.mc_order_couplings = self.get_order_couplings(order_couplings)
        orders = [cast(Order, obj) for obj in input_data.order]
        self.mc_orders = self.get_orders(orders, self.mc_order_couplings)
        market_areas = [cast(MarketArea, obj) for obj in input_data.market_area]
        self.mc_market_areas = self.get_market_areas(market_areas, self.mc_orders)
        market_borders = [cast(MarketBorder, obj) for obj in input_data.market_border]
        self.mc_market_borders = self.get_market_borders(market_borders)
        control_blocks = [cast(ControlBlock, obj) for obj in input_data.control_block]
        self.mc_control_blocks = self.get_control_blocks(control_blocks)

        if self.parameters.exchange_constraints_type == ExchangeConstraintsType.FB:
            critical_branches = [cast(CriticalBranch, obj) for obj in input_data.critical_branch]
            self.mc_critical_branches = self.get_critical_branches(critical_branches)
            market_area_ptdfs = [cast(MarketAreaPtdf, obj) for obj in input_data.market_area_ptdf]
            self.mc_market_area_ptdfs = self.get_market_area_ptdfs(market_area_ptdfs)
        else:
            self.mc_critical_branches = {}
            self.mc_market_area_ptdfs = {}

    def get_critical_branches(self, critical_branches: list[CriticalBranch]) -> dict[str, CriticalBranchMC]:
        return {
            critical_branch.name: CriticalBranchMC.model_validate(dict(critical_branch))
            for critical_branch in critical_branches
        }

    def get_control_blocks(self, control_blocks: list[ControlBlock]) -> dict[str, ControlBlock]:
        # filter by the parameters control_block_names
        if self.parameters.control_block_names == "all":
            control_blocks_to_keep = control_blocks
        else:
            control_blocks_to_keep = [
                control_block
                for control_block in control_blocks
                if control_block.name in self.parameters.control_block_names
            ]
        # filter by the present market_area
        present_control_block_names = {
            mc_market_area.control_block.name for mc_market_area in self.mc_market_areas.values()
        }
        control_blocks_mc = {}
        for control_block in control_blocks_to_keep:
            if control_block.name in present_control_block_names:
                control_blocks_mc[control_block.name] = ControlBlock.model_validate(dict(control_block))
        return control_blocks_mc

    def get_market_areas(
        self, market_areas: list[MarketArea], mc_orders: dict[str, OrderMC]
    ) -> dict[str, MarketAreaMC]:
        if self.parameters.market_area_names == "all":
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
            market_area_dump = {**dict(market_area), "mc_orders": market_area_orders}
            mc_market_area = MarketAreaMC.model_validate(market_area_dump)
            mc_market_areas[market_area.name] = mc_market_area

        return mc_market_areas

    def get_orders(self, orders: list[Order], order_couplings: dict[str, OrderCouplingMC]) -> dict[str, OrderMC]:
        mc_orders = {}
        for order in orders:
            if not OrderMC.is_feasible(order, self.times, self.parameters):
                continue
            requires_status_variable = (
                True if order.qmin and order.qmin > self.parameters.allowed_round_off_error else False
            )
            order_dump = {
                **dict(order),
                "timestep": self.parameters.temporal.timestep,
                "requires_status_variable": requires_status_variable,
            }
            mc_order = OrderMC.model_validate(order_dump)
            # is_feasible already checked start_date is on the optimization grid, so it's always found:
            mc_order.time_index = self.times.index(mc_order.start_date)
            mc_orders[order.name] = mc_order

        for order_coupling in order_couplings.values():
            for order in order_coupling.orders:
                if order.name not in mc_orders:
                    continue
                _apply_coupling_flags(mc_orders[order.name], order_coupling)
            if order_coupling.coupling_type == CouplingType.PARENT_CHILDREN and order_coupling.orders:
                parent_order = order_coupling.orders[0]
                mc_parent = mc_orders[parent_order.name]
                mc_parent.is_parent = True
                parent_ids = mc_parent.order_coupling_parent_ids or []
                parent_ids.append(order_coupling.name)
                mc_parent.order_coupling_parent_ids = parent_ids

        return mc_orders

    def get_order_couplings(self, order_couplings: list[OrderCoupling]) -> dict[str, OrderCouplingMC]:
        mc_order_couplings = {}
        for order_coupling in order_couplings:
            if self.is_order_coupling_feasible(order_coupling):
                order_coupling_dump = dict(order_coupling)
                mc_order_coupling = OrderCouplingMC.model_validate(order_coupling_dump)
                mc_order_couplings[order_coupling.name] = mc_order_coupling
        return mc_order_couplings

    def is_order_coupling_feasible(self, order_coupling: OrderCoupling) -> bool:
        if order_coupling.orders is None:
            return False
        order_names = [
            order.name for order in order_coupling.orders if OrderMC.is_feasible(order, self.times, self.parameters)
        ]
        return len(order_names) >= 2

    def get_market_borders(self, market_borders: list[MarketBorder]) -> dict[str, MarketBorderMC]:
        mc_market_borders = {}
        for market_border in market_borders:
            if self.parameters.market_area_names != "all":
                if (
                    market_border.uphill_market_area is None
                    or market_border.uphill_market_area.name not in self.parameters.market_area_names
                ):
                    continue
                if (
                    market_border.downhill_market_area is None
                    or market_border.downhill_market_area.name not in self.parameters.market_area_names
                ):
                    continue
            mc_market_border = MarketBorderMC.model_validate(dict(market_border))
            mc_market_borders[market_border.name] = mc_market_border
        return mc_market_borders

    def get_market_area_ptdfs(self, market_area_ptdfs: list[MarketAreaPtdf]) -> dict[str, MarketAreaPtdfMC]:
        return {
            market_area_ptdf.name: MarketAreaPtdfMC.model_validate(dict(market_area_ptdf))
            for market_area_ptdf in market_area_ptdfs
        }
