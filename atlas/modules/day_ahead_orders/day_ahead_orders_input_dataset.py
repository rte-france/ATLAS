"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import (
    BusinessModel,
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
from atlas.config import INVERSE_MODEL_MAPPING_NAME
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class DayAheadOrdersInputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, raw_data: dict[str, list[BusinessModel]], parameters: DayAheadOrdersParameters):
        self.raw_data = raw_data
        self.parameters = parameters

        self.control_block = raw_data[INVERSE_MODEL_MAPPING_NAME[ControlBlock]]
        self.market_area = raw_data[INVERSE_MODEL_MAPPING_NAME[MarketArea]]
        self.market_border = raw_data[INVERSE_MODEL_MAPPING_NAME[MarketBorder]]
        self.node = raw_data[INVERSE_MODEL_MAPPING_NAME[Node]]
        self.portfolio = raw_data[INVERSE_MODEL_MAPPING_NAME[Portfolio]]
        self.wind = raw_data[INVERSE_MODEL_MAPPING_NAME[Wind]]
        self.storage = raw_data[INVERSE_MODEL_MAPPING_NAME[Storage]]
        self.hydro = raw_data[INVERSE_MODEL_MAPPING_NAME[Hydro]]
        self.solar = raw_data[INVERSE_MODEL_MAPPING_NAME[Solar]]
        self.thermal = raw_data[INVERSE_MODEL_MAPPING_NAME[Thermal]]
        self.other_non_dispatchable = raw_data[INVERSE_MODEL_MAPPING_NAME[OtherNonDispatchable]]
        self.order = raw_data[INVERSE_MODEL_MAPPING_NAME[Order]]
        self.order_coupling = raw_data[INVERSE_MODEL_MAPPING_NAME[OrderCoupling]]
        self.load = raw_data[INVERSE_MODEL_MAPPING_NAME[Load]]

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
