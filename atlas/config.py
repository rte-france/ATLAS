"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from atlas.logging import Logger
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

logger = Logger().get_logger()

MODEL_MAPPING_NAME: dict[str, Any] = {
    "control_block": ControlBlock,
    "critical_branch": CriticalBranch,
    "equipment": Equipment,
    "hydro": Hydro,
    "load": Load,
    "market_area": MarketArea,
    "market_area_ptdf": MarketAreaPtdf,
    "market_border": MarketBorder,
    "node": Node,
    "node_ptdf": NodePtdf,
    "order": Order,
    "order_coupling": OrderCoupling,
    "other_non_dispatchable": OtherNonDispatchable,
    "solar": Solar,
    "portfolio": Portfolio,
    "storage": Storage,
    "thermal": Thermal,
    "wind": Wind,
}
