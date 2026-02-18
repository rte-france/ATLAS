"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

from atlas import (
    AtlasDataset,
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
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


class DayAheadOrdersInputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, raw_data: AtlasDataset, parameters: DayAheadOrdersParameters):
        self.parameters: DayAheadOrdersParameters = parameters
        self.control_block: list[ControlBlock] = [cast(ControlBlock, obj) for obj in raw_data.control_block]
        self.market_area: list[MarketArea] = [cast(MarketArea, obj) for obj in raw_data.market_area]
        self.market_border: list[MarketBorder] = [cast(MarketBorder, obj) for obj in raw_data.market_border]
        self.node: list[Node] = [cast(Node, obj) for obj in raw_data.node]
        self.portfolio: list[Portfolio] = [cast(Portfolio, obj) for obj in raw_data.portfolio]
        self.wind: list[Wind] = [cast(Wind, obj) for obj in raw_data.wind]
        self.storage: list[Storage] = [cast(Storage, obj) for obj in raw_data.storage]
        self.hydro: list[Hydro] = [cast(Hydro, obj) for obj in raw_data.hydro]
        self.solar: list[Solar] = [cast(Solar, obj) for obj in raw_data.solar]
        self.thermal: list[Thermal] = [cast(Thermal, obj) for obj in raw_data.thermal]
        self.other_non_dispatchable: list[OtherNonDispatchable] = [
            cast(OtherNonDispatchable, obj) for obj in raw_data.other_non_dispatchable
        ]
        self.load: list[Load] = [cast(Load, obj) for obj in raw_data.load]

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
