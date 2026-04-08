"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.enums import BusinessModelName
from atlas.log import Logger
from atlas.objects.business_model import BusinessModel
from atlas.objects.equipment.equipment import Equipment
from atlas.objects.equipment.hydro import Hydro
from atlas.objects.equipment.load import Load
from atlas.objects.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.objects.equipment.solar import Solar
from atlas.objects.equipment.storage import Storage
from atlas.objects.equipment.thermal import Thermal
from atlas.objects.equipment.wind import Wind
from atlas.objects.market.critical_branch import CriticalBranch
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market.market_area_ptdf import MarketAreaPtdf
from atlas.objects.market.market_border import MarketBorder
from atlas.objects.market.node_ptdf import NodePtdf
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.objects.network_operator.control_block import ControlBlock

logger = Logger().get_logger()


MODEL_MAPPING_NAME: dict[BusinessModelName, type[BusinessModel]] = {
    BusinessModelName.CONTROL_BLOCK: ControlBlock,
    BusinessModelName.CRITICAL_BRANCH: CriticalBranch,
    BusinessModelName.EQUIPMENT: Equipment,
    BusinessModelName.HYDRO: Hydro,
    BusinessModelName.LOAD: Load,
    BusinessModelName.MARKET_AREA: MarketArea,
    BusinessModelName.MARKET_AREA_PTDF: MarketAreaPtdf,
    BusinessModelName.MARKET_BORDER: MarketBorder,
    BusinessModelName.NODE: Node,
    BusinessModelName.NODE_PTDF: NodePtdf,
    BusinessModelName.ORDER: Order,
    BusinessModelName.ORDER_COUPLING: OrderCoupling,
    BusinessModelName.OTHER_NON_DISPATCHABLE: OtherNonDispatchable,
    BusinessModelName.SOLAR: Solar,
    BusinessModelName.PORTFOLIO: Portfolio,
    BusinessModelName.STORAGE: Storage,
    BusinessModelName.THERMAL: Thermal,
    BusinessModelName.WIND: Wind,
}


INVERSE_MODEL_MAPPING_NAME: dict[type[BusinessModel], BusinessModelName] = {
    model: name for name, model in MODEL_MAPPING_NAME.items()
}


EQUIPMENT_MODELS = [
    BusinessModelName.WIND,
    BusinessModelName.STORAGE,
    BusinessModelName.HYDRO,
    BusinessModelName.SOLAR,
    BusinessModelName.THERMAL,
    BusinessModelName.OTHER_NON_DISPATCHABLE,
    BusinessModelName.LOAD,
]


MODEL_ORDER_INSTANTIATION = (
    [
        BusinessModelName.CONTROL_BLOCK,
        BusinessModelName.MARKET_AREA,
        BusinessModelName.MARKET_AREA_PTDF,
        BusinessModelName.MARKET_BORDER,
        BusinessModelName.NODE,
        BusinessModelName.NODE_PTDF,
        BusinessModelName.PORTFOLIO,
    ]
    + EQUIPMENT_MODELS
    + [
        BusinessModelName.ORDER,
        BusinessModelName.ORDER_COUPLING,
    ]
    + [BusinessModelName.CRITICAL_BRANCH]
)


DEFAULT_VALUE_IO = {
    BusinessModelName.EQUIPMENT: {
        "setup_delay": 0,
        "unit_count": 1,
        "maximum_gradient": 0,
    },
    BusinessModelName.STORAGE: {
        "transition_duration": "P0D",
    },
    BusinessModelName.MARKET_BORDER: {
        "coupling_type": "ATC",
    },
}
