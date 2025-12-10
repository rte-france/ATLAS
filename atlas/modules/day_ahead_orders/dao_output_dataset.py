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


class DayAheadOrdersOutputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, inputDataset: DayAheadOrdersInputDataset):
        self.parameters = copy.deepcopy(inputDataset.parameters)
        self.control_block = copy.deepcopy(inputDataset.control_block)
        self.market_area = copy.deepcopy(inputDataset.market_area)
        self.market_border = copy.deepcopy(inputDataset.market_border)
        self.node = copy.deepcopy(inputDataset.node)
        self.portfolio = copy.deepcopy(inputDataset.portfolio)
        self.wind = copy.deepcopy(inputDataset.wind)
        self.storage = copy.deepcopy(inputDataset.storage)
        self.hydro = copy.deepcopy(inputDataset.hydro)
        self.solar = copy.deepcopy(inputDataset.solar)
        self.thermal = copy.deepcopy(inputDataset.thermal)
        self.other_non_dispatchable = copy.deepcopy(inputDataset.other_non_dispatchable)
        self.load = copy.deepcopy(inputDataset.load)
        self.order: list[Order] = []
        self.order_coupling: list[OrderCoupling] = []

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
