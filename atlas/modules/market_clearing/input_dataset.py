"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.dataset import AbstractDataset
from atlas.config import logger
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


class MarketClearingInputDataset(AbstractDataset[MarketClearingParameters]):
    """Input dataset for Market Clearing module"""

    def __init__(self, input_data: AtlasDataset, parameters: MarketClearingParameters):
        self.input_data = input_data
        self.parameters = parameters
        self.times = generate_datetimes(
            self.parameters.temporal.start_date,
            self.parameters.temporal.end_date - self.parameters.temporal.timestep,
            self.parameters.temporal.timestep,
        )

        self.is_atc = self.parameters.exchange_constraints_type == ExchangeConstraintsType.ATC

        self.order_couplings = self.get_order_couplings(input_data.order_coupling.all())
        self.orders = self.get_orders(input_data.order.all(), self.order_couplings)
        self.market_areas = self.get_market_areas(input_data.market_area.all(), self.orders)
        self.market_borders = self.get_market_borders(input_data.market_border.all())
        self.control_blocks = self.get_control_blocks(input_data.control_block.all())

        if self.parameters.exchange_constraints_type == ExchangeConstraintsType.FB:
            self.critical_branches = self.get_critical_branches(input_data.critical_branch.all())
            self.market_area_ptdfs = self.get_market_area_ptdfs(input_data.market_area_ptdf.all())
        else:
            self.critical_branches = {}
            self.market_area_ptdfs = {}

    def get_critical_branches(self, critical_branches: list[CriticalBranch]) -> dict[str, CriticalBranchMC]:
        if not critical_branches:
            return {}
        mc_critical_branches = {}
        for critical_branch in critical_branches:
            critical_branch_dump = {
                **dict(critical_branch),
                "timestep": self.parameters.temporal.timestep,
                "times": self.times,
            }
            mc_critical_branch = CriticalBranchMC.model_validate(critical_branch_dump)
            mc_critical_branches[critical_branch.name] = mc_critical_branch
        return mc_critical_branches

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
        control_blocks_mc = {}
        for control_block in control_blocks_to_keep:
            for market_area in self.market_areas.values():
                if control_block == market_area.control_block:
                    mc_control_block = ControlBlock(**dict(control_block))
                    control_blocks_mc[control_block.name] = mc_control_block
        return control_blocks_mc

    def get_market_areas(self, market_areas: list[MarketArea], orders: dict[str, OrderMC]) -> dict[str, MarketAreaMC]:
        if self.parameters.market_area_names == "all":
            market_areas_to_keep = market_areas
        else:
            market_areas_to_keep = [
                market_area for market_area in market_areas if market_area.name in self.parameters.market_area_names
            ]
        mc_market_areas = {}
        for market_area in market_areas_to_keep:
            market_area_orders = {
                order_name: order for order_name, order in orders.items() if order.market_area.name == market_area.name
            }
            market_area_dump = {
                **dict(market_area),
                "timestep": self.parameters.temporal.timestep,
                "times": self.times,
                "orders": market_area_orders,
            }
            mc_market_area = MarketAreaMC.model_validate(market_area_dump)
            mc_market_areas[market_area.name] = mc_market_area

        return mc_market_areas

    def get_orders(self, orders: list[Order], order_couplings: dict[str, OrderCouplingMC]) -> dict[str, OrderMC]:
        mc_orders = {}
        for order in orders:
            if OrderMC.is_feasible(order, self.times, self.parameters):
                requires_status_variable = (
                    True if order.qmin and order.qmin > self.parameters.allowed_round_off_error else False
                )
                order_dump = {
                    **dict(order),
                    "timestep": self.parameters.temporal.timestep,
                    "requires_status_variable": requires_status_variable,
                }
                order = OrderMC.model_validate(order_dump)
                # Add time_index attribute -> use in pricing and output
                time_index = None
                for candidate_time_index, time in enumerate(self.times):
                    if time == order.start_date:
                        time_index = candidate_time_index
                        break
                if time_index is None:
                    logger.debug(f"Order {order.name} is ignored : The start date is not an optimization timestep.")
                    continue
                order.time_index = time_index
                mc_orders[order.name] = order

        for order_coupling in order_couplings.values():
            for order in order_coupling.orders:
                if order.name not in mc_orders:
                    continue
                order = mc_orders[order.name]
                if order_coupling.coupling_type == CouplingType.EXCLUSION:
                    order.requires_status_variable = True
                    order.is_mutually_excluding = True
                if order_coupling.coupling_type == CouplingType.IDENTICAL_VOLUME:
                    order.is_linked = True
                    order.link_id = order_coupling.name
                if order_coupling.coupling_type == CouplingType.IDENTICAL_RATIO:
                    order.is_linked = True
                    order.link_id = order_coupling.name
                # Uncomment to enforce the PC constraint
                if order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                    order.is_in_parent_child_coupling = True
                    order.requires_status_variable = True
                    order.parent_child_id = order_coupling.name
                if order_coupling.coupling_type == CouplingType.COMPLEMENT:
                    order.is_linked = True
                    order.link_id = order_coupling.name
            if order_coupling.coupling_type == CouplingType.PARENT_CHILDREN:
                if len(order_coupling.orders) > 0:
                    order = order_coupling.orders[0]
                    mc_orders[order.name].is_parent = True
                    parent_ids = mc_orders[order.name].order_coupling_parent_ids
                    if parent_ids is None:
                        parent_ids = []
                    parent_ids.append(order_coupling.name)
                    mc_orders[order.name].order_coupling_parent_ids = parent_ids

        return mc_orders

    def get_order_couplings(self, order_couplings: list[OrderCoupling]) -> dict[str, OrderCouplingMC]:
        mc_order_couplings = {}
        for order_coupling in order_couplings:
            if self.is_order_coupling_feasible(order_coupling):
                mc_order_coupling = OrderCouplingMC(**dict(order_coupling))
                mc_order_couplings[order_coupling.name] = mc_order_coupling
        return mc_order_couplings

    def is_order_coupling_feasible(self, order_coupling: OrderCoupling) -> bool:
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
            market_border_dump = {
                **dict(market_border),
                "timestep": self.parameters.temporal.timestep,
                "times": self.times,
            }
            market_border = MarketBorderMC(**market_border_dump)
            mc_market_borders[market_border.name] = market_border
        return mc_market_borders

    def get_market_area_ptdfs(self, market_area_ptdfs: list[MarketAreaPtdf]) -> dict[str, MarketAreaPtdfMC]:
        mc_market_area_ptdfs = {}
        for market_area_ptdf in market_area_ptdfs:
            market_area_ptdf_dump = {
                **dict(market_area_ptdf),
                "timestep": self.parameters.temporal.timestep,
                "times": self.times,
            }
            mc_market_area_ptdf = MarketAreaPtdfMC.model_validate(market_area_ptdf_dump)
            mc_market_area_ptdfs[market_area_ptdf.name] = mc_market_area_ptdf
        return mc_market_area_ptdfs
