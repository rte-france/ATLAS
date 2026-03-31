"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import TypeVar

from atlas import AtlasDataset, ControlBlock
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.market.market_area import MarketArea
from atlas.modules.day_ahead_orders.models.hydro import HydroDAO
from atlas.modules.day_ahead_orders.models.load import LoadDAO
from atlas.modules.day_ahead_orders.models.portfolio import PortfolioDAO
from atlas.modules.day_ahead_orders.models.solar import SolarDAO
from atlas.modules.day_ahead_orders.models.storage import StorageDAO
from atlas.modules.day_ahead_orders.models.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.models.wind import WindDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters

T = TypeVar("T")


class DayAheadOrdersInputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, input_data: AtlasDataset, parameters: DayAheadOrdersParameters):
        self.parameters: DayAheadOrdersParameters = parameters

        self.control_block: list[ControlBlock] = input_data.control_block.all()
        self.other_non_dispatchable: list[OtherNonDispatchable] = input_data.other_non_dispatchable.all()
        self.market_area: list[MarketArea] = input_data.market_area.all()

        self.portfolio: list[PortfolioDAO] = [PortfolioDAO(**dict(obj)) for obj in input_data.portfolio]
        self.wind: list[WindDAO] = [WindDAO.model_validate(obj) for obj in input_data.wind]
        self.storage: list[StorageDAO] = [StorageDAO.model_validate(obj) for obj in input_data.storage]
        self.hydro: list[HydroDAO] = [HydroDAO.model_validate(obj) for obj in input_data.hydro]
        self.solar: list[SolarDAO] = [SolarDAO.model_validate(obj) for obj in input_data.solar]
        self.thermal: list[ThermalDAO] = [ThermalDAO.model_validate(obj) for obj in input_data.thermal]
        self.load: list[LoadDAO] = [LoadDAO.model_validate(obj) for obj in input_data.load]
