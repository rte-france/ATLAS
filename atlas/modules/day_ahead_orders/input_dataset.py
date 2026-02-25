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
    OtherNonDispatchable,
)
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.modules.day_ahead_orders.models.hydro import HydroDAO
from atlas.modules.day_ahead_orders.models.load import LoadDAO
from atlas.modules.day_ahead_orders.models.market_area import MarketAreaDAO
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO
from atlas.modules.day_ahead_orders.models.solar import SolarDAO
from atlas.modules.day_ahead_orders.models.storage import StorageDAO
from atlas.modules.day_ahead_orders.models.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.models.wind import WindDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


class DayAheadOrdersInputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, raw_data: AtlasDataset, parameters: DayAheadOrdersParameters):
        self.parameters: DayAheadOrdersParameters = parameters
        self.control_block: list[ControlBlock] = list(raw_data.control_block)
        self.market_area: list[MarketAreaDAO] = [cast(MarketAreaDAO, obj) for obj in raw_data.market_area]
        self.portfolio: list[PortfolioDAO] = [cast(PortfolioDAO, obj) for obj in raw_data.portfolio]
        self.wind: list[WindDAO] = [cast(WindDAO, obj) for obj in raw_data.wind]
        self.storage: list[StorageDAO] = [cast(StorageDAO, obj) for obj in raw_data.storage]
        self.hydro: list[HydroDAO] = [cast(HydroDAO, obj) for obj in raw_data.hydro]
        self.solar: list[SolarDAO] = [cast(SolarDAO, obj) for obj in raw_data.solar]
        self.thermal: list[ThermalDAO] = [cast(ThermalDAO, obj) for obj in raw_data.thermal]
        self.other_non_dispatchable: list[OtherNonDispatchable] = [
            cast(OtherNonDispatchable, obj) for obj in raw_data.other_non_dispatchable
        ]
        self.load: list[LoadDAO] = [cast(LoadDAO, obj) for obj in raw_data.load]

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
