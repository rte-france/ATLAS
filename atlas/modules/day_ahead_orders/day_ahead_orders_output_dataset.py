"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class DayAheadOrdersOutputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, inputDataset: DayAheadOrdersInputDataset):
        self.raw_data = inputDataset.raw_data
        self.parameters = inputDataset.parameters

        self.control_block = inputDataset.control_block
        self.market_area = inputDataset.market_area
        self.market_border = inputDataset.market_border
        self.node = inputDataset.node
        self.portfolio = inputDataset.portfolio
        self.wind = inputDataset.wind
        self.storage = inputDataset.storage
        self.hydro = inputDataset.hydro
        self.solar = inputDataset.solar
        self.thermal = inputDataset.thermal
        self.other_non_dispatchable = inputDataset.other_non_dispatchable
        self.order = inputDataset.order
        self.order_coupling = inputDataset.order_coupling
        self.load = inputDataset.load

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
