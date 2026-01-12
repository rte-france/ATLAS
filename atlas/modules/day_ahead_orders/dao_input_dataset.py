"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

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
    def __init__(self, raw_data: dict[str, list[type[BusinessModel]]], parameters: DayAheadOrdersParameters):
        self.parameters: DayAheadOrdersParameters = parameters
        self.control_block: list[ControlBlock] = (
            [cast(ControlBlock, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[ControlBlock]]]
            if INVERSE_MODEL_MAPPING_NAME[ControlBlock] in raw_data
            else []
        )
        self.market_area: list[MarketArea] = (
            [cast(MarketArea, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[MarketArea]]]
            if INVERSE_MODEL_MAPPING_NAME[MarketArea] in raw_data
            else []
        )
        self.market_border: list[MarketBorder] = (
            [cast(MarketBorder, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[MarketBorder]]]
            if INVERSE_MODEL_MAPPING_NAME[MarketBorder] in raw_data
            else []
        )
        self.node: list[Node] = (
            [cast(Node, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Node]]]
            if INVERSE_MODEL_MAPPING_NAME[Node] in raw_data
            else []
        )
        self.portfolio: list[Portfolio] = (
            [cast(Portfolio, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Portfolio]]]
            if INVERSE_MODEL_MAPPING_NAME[Portfolio] in raw_data
            else []
        )
        self.wind: list[Wind] = (
            [cast(Wind, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Wind]]]
            if INVERSE_MODEL_MAPPING_NAME[Wind] in raw_data
            else []
        )
        self.storage: list[Storage] = (
            [cast(Storage, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Storage]]]
            if INVERSE_MODEL_MAPPING_NAME[Wind] in raw_data
            else []
        )
        self.hydro: list[Hydro] = (
            [cast(Hydro, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Hydro]]]
            if INVERSE_MODEL_MAPPING_NAME[Hydro] in raw_data
            else []
        )
        self.solar: list[Solar] = (
            [cast(Solar, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Solar]]]
            if INVERSE_MODEL_MAPPING_NAME[Solar] in raw_data
            else []
        )
        self.thermal: list[Thermal] = (
            [cast(Thermal, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Thermal]]]
            if INVERSE_MODEL_MAPPING_NAME[Thermal] in raw_data
            else []
        )
        self.other_non_dispatchable: list[OtherNonDispatchable] = (
            [cast(OtherNonDispatchable, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[OtherNonDispatchable]]]
            if INVERSE_MODEL_MAPPING_NAME[OtherNonDispatchable] in raw_data
            else []
        )
        self.load: list[Load] = (
            [cast(Load, obj) for obj in raw_data[INVERSE_MODEL_MAPPING_NAME[Load]]]
            if INVERSE_MODEL_MAPPING_NAME[Load] in raw_data
            else []
        )

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
