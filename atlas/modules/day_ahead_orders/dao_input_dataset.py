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
    OtherNonDispatchable,
    Portfolio,
    Solar,
    Storage,
    Thermal,
    Wind,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.config import INVERSE_MODEL_MAPPING_NAME
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters


class DayAheadOrdersInputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, raw_data: dict[str, list[BusinessModel]], parameters: DayAheadOrdersParameters):
        self.raw_data = raw_data
        self.parameters = parameters

        self.control_block = (
            raw_data[INVERSE_MODEL_MAPPING_NAME[ControlBlock]]
            if INVERSE_MODEL_MAPPING_NAME[ControlBlock] in raw_data
            else []
        )
        self.market_area = (
            raw_data[INVERSE_MODEL_MAPPING_NAME[MarketArea]]
            if INVERSE_MODEL_MAPPING_NAME[MarketArea] in raw_data
            else []
        )
        self.market_border = (
            raw_data[INVERSE_MODEL_MAPPING_NAME[MarketBorder]]
            if INVERSE_MODEL_MAPPING_NAME[MarketBorder] in raw_data
            else []
        )
        self.node = raw_data[INVERSE_MODEL_MAPPING_NAME[Node]] if INVERSE_MODEL_MAPPING_NAME[Node] in raw_data else []
        self.portfolio = (
            raw_data[INVERSE_MODEL_MAPPING_NAME[Portfolio]] if INVERSE_MODEL_MAPPING_NAME[Portfolio] in raw_data else []
        )
        self.wind = raw_data[INVERSE_MODEL_MAPPING_NAME[Wind]] if INVERSE_MODEL_MAPPING_NAME[Wind] in raw_data else []
        self.storage = (
            raw_data[INVERSE_MODEL_MAPPING_NAME[Storage]] if INVERSE_MODEL_MAPPING_NAME[Wind] in raw_data else []
        )
        self.hydro = (
            raw_data[INVERSE_MODEL_MAPPING_NAME[Hydro]] if INVERSE_MODEL_MAPPING_NAME[Hydro] in raw_data else []
        )
        self.solar = (
            raw_data[INVERSE_MODEL_MAPPING_NAME[Solar]] if INVERSE_MODEL_MAPPING_NAME[Solar] in raw_data else []
        )
        self.thermal = (
            raw_data[INVERSE_MODEL_MAPPING_NAME[Thermal]] if INVERSE_MODEL_MAPPING_NAME[Thermal] in raw_data else []
        )
        self.other_non_dispatchable = (
            raw_data[INVERSE_MODEL_MAPPING_NAME[OtherNonDispatchable]]
            if INVERSE_MODEL_MAPPING_NAME[OtherNonDispatchable] in raw_data
            else []
        )
        self.load = raw_data[INVERSE_MODEL_MAPPING_NAME[Load]] if INVERSE_MODEL_MAPPING_NAME[Load] in raw_data else []

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
