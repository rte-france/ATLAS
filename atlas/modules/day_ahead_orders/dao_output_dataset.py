"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import copy

from atlas import (
    ControlBlock,
    Hydro,
    Load,
    MarketArea,
    MarketBorder,
    Node,
    Order,
    OrderCoupling,
    OtherNonDispatchable,
    Portfolio,
    Solar,
    Storage,
    Thermal,
    Wind,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.models.business_model import BusinessModel
from atlas.modules.day_ahead_orders.dao_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.orders_formulation.models.order import OrderDAO
from atlas.modules.day_ahead_orders.orders_formulation.models.order_coupling import OrderCouplingDAO


class DayAheadOrdersOutputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, inputDataset: DayAheadOrdersInputDataset):
        self.parameters: DayAheadOrdersParameters = copy.deepcopy(inputDataset.parameters)
        self.control_block: list[ControlBlock] = copy.deepcopy(inputDataset.control_block)
        self.market_area: list[MarketArea] = copy.deepcopy(inputDataset.market_area)
        self.market_border: list[MarketBorder] = copy.deepcopy(inputDataset.market_border)
        self.node: list[Node] = copy.deepcopy(inputDataset.node)
        self.portfolio: list[Portfolio] = copy.deepcopy(inputDataset.portfolio)
        self.wind: list[Wind] = copy.deepcopy(inputDataset.wind)
        self.storage: list[Storage] = copy.deepcopy(inputDataset.storage)
        self.hydro: list[Hydro] = copy.deepcopy(inputDataset.hydro)
        self.solar: list[Solar] = copy.deepcopy(inputDataset.solar)
        self.thermal: list[Thermal] = copy.deepcopy(inputDataset.thermal)
        self.other_non_dispatchable: list[OtherNonDispatchable] = copy.deepcopy(inputDataset.other_non_dispatchable)
        self.load: list[Load] = copy.deepcopy(inputDataset.load)
        self.order: list[OrderDAO] = []
        self.order_coupling: list[OrderCouplingDAO] = []

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return [
            ControlBlock,
            MarketArea,
            MarketBorder,
            Node,
            Portfolio,
            Wind,
            Storage,
            Hydro,
            Solar,
            Thermal,
            Load,
            Order,
            OrderCoupling,
        ]
