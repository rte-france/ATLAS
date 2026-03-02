"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import (
    AtlasDataset,
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
        self.control_block: list[ControlBlock] = raw_data.control_block.all()
        self.market_area: list[MarketAreaDAO] = [MarketAreaDAO(**dict(obj)) for obj in raw_data.market_area]
        self.portfolio: list[PortfolioDAO] = [PortfolioDAO(**dict(obj)) for obj in raw_data.portfolio]
        self.wind: list[WindDAO] = [WindDAO(**dict(obj)) for obj in raw_data.wind]
        self.storage: list[StorageDAO] = [StorageDAO(**dict(obj)) for obj in raw_data.storage]
        self.hydro: list[HydroDAO] = [HydroDAO(**dict(obj)) for obj in raw_data.hydro]
        self.solar: list[SolarDAO] = [SolarDAO(**dict(obj)) for obj in raw_data.solar]
        self.thermal: list[ThermalDAO] = [ThermalDAO(**dict(obj)) for obj in raw_data.thermal]
        self.other_non_dispatchable: list[OtherNonDispatchable] = [
            OtherNonDispatchable(**dict(obj)) for obj in raw_data.other_non_dispatchable
        ]
        self.load: list[LoadDAO] = [LoadDAO(**dict(obj)) for obj in raw_data.load]
