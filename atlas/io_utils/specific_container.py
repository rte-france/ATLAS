"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from collections.abc import Iterable

from atlas.io_utils.container import Container
from atlas.models.control_block import ControlBlock
from atlas.models.equipment.equipment import Equipment
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
    def __init__(self, items: Iterable[ControlBlock] | None = None):
        super().__init__(items)


class CriticalBranchContainer(Container[CriticalBranch]):
    def __init__(self, items: Iterable[CriticalBranch] | None = None):
        super().__init__(items)


class EquipmentContainer(Container[Equipment]):
    def __init__(self, items: Iterable[Equipment] | None = None):
        super().__init__(items)


class HydroContainer(EquipmentContainer):
    def __init__(self, items: Iterable[Equipment] | None = None):
        super().__init__(items)


class LoadContainer(EquipmentContainer):
    def __init__(self, items: Iterable[Equipment] | None = None):
        super().__init__(items)


class MarketAreaContainer(Container[MarketArea]):
    def __init__(self, items: Iterable[MarketArea] | None = None):
        super().__init__(items)


class MarketAreaPtdfContainer(Container[MarketAreaPtdf]):
    def __init__(self, items: Iterable[MarketAreaPtdf] | None = None):
        super().__init__(items)


class MarketBorderContainer(Container[MarketBorder]):
    def __init__(self, items: Iterable[MarketBorder] | None = None):
        super().__init__(items)


class NodeContainer(Container[Node]):
    def __init__(self, items: Iterable[Node] | None = None):
        super().__init__(items)


class NodePtdfContainer(Container[NodePtdf]):
    def __init__(self, items: Iterable[NodePtdf] | None = None):
        super().__init__(items)


class OrderContainer(Container[Order]):
    def __init__(self, items: Iterable[Order] | None = None):
        super().__init__(items)


class OrderCouplingContainer(Container[OrderCoupling]):
    def __init__(self, items: Iterable[OrderCoupling] | None = None):
        super().__init__(items)


class OtherNonDispatchableContainer(EquipmentContainer):
    def __init__(self, items: Iterable[Equipment] | None = None):
        super().__init__(items)


class SolarContainer(EquipmentContainer):
    def __init__(self, items: Iterable[Equipment] | None = None):
        super().__init__(items)


class PortfolioContainer(Container[Portfolio]):
    def __init__(self, items: Iterable[Portfolio] | None = None):
        super().__init__(items)


class StorageContainer(EquipmentContainer):
    def __init__(self, items: Iterable[Equipment] | None = None):
        super().__init__(items)


class ThermalContainer(EquipmentContainer):
    def __init__(self, items: Iterable[Equipment] | None = None):
        super().__init__(items)


class WindContainer(EquipmentContainer):
    def __init__(self, items: Iterable[Equipment] | None = None):
        super().__init__(items)
