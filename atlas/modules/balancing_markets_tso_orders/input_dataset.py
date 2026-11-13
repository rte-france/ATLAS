"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import TypeVar

from atlas import ControlBlock, MarketArea, Order, OrderCoupling
from atlas.abstract_class.dataset import AbstractDataset
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.balancing_markets_tso_orders.parameters import TSOOrdersParameters

T = TypeVar("T")


class TSOOrdersInputDataset(AbstractDataset[TSOOrdersParameters]):
    def __init__(self, input_data: AtlasDataset, parameters: TSOOrdersParameters):
        self.parameters: TSOOrdersParameters = parameters

        self.control_block: list[ControlBlock] = input_data.control_block.all()
        self.market_area: list[MarketArea] = input_data.market_area.all()
        self.order_coupling: list[OrderCoupling] = input_data.order_coupling.all()
        self.bsp_order: list[Order] = input_data.order.all()
        # self.equipment: list[Equipment] = input_data.equipment.all()
