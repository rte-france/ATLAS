"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.io_utils.container import Container
from atlas.models.control_block import ControlBlock
from atlas.models.equipment.equipment import Equipment
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.thermal import Thermal
from atlas.models.equipment.wind import Wind
from atlas.models.market.critical_branch import CriticalBranch
from atlas.models.market.market_area import MarketArea
from atlas.models.market.market_area_ptdf import MarketAreaPtdf
from atlas.models.market.market_border import MarketBorder
from atlas.models.market.node_ptdf import NodePtdf
from atlas.models.market.order import Order
from atlas.models.market.order_coupling import OrderCoupling
from atlas.models.node import Node
from atlas.models.portfolio import Portfolio


class ControlBlockContainer(Container[ControlBlock]):
    item_type = ControlBlock


class CriticalBranchContainer(Container[CriticalBranch]):
    item_type = CriticalBranch


class EquipmentContainer(Container[Equipment]):
    item_type = Equipment


class HydroContainer(Container[Hydro]):
    item_type = Hydro


class LoadContainer(Container[Load]):
    item_type = Load


class MarketAreaContainer(Container[MarketArea]):
    item_type = MarketArea


class MarketAreaPtdfContainer(Container[MarketAreaPtdf]):
    item_type = MarketAreaPtdf


class MarketBorderContainer(Container[MarketBorder]):
    item_type = MarketBorder


class NodeContainer(Container[Node]):
    item_type = Node


class NodePtdfContainer(Container[NodePtdf]):
    item_type = NodePtdf


class OrderContainer(Container[Order]):
    item_type = Order


class OrderCouplingContainer(Container[OrderCoupling]):
    item_type = OrderCoupling


class OtherNonDispatchableContainer(Container[OtherNonDispatchable]):
    item_type = OtherNonDispatchable


class SolarContainer(Container[Solar]):
    item_type = Solar


class PortfolioContainer(Container[Portfolio]):
    item_type = Portfolio


class StorageContainer(Container[Storage]):
    item_type = Storage


class ThermalContainer(Container[Thermal]):
    item_type = Thermal


class WindContainer(Container[Wind]):
    item_type = Wind
