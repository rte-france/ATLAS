"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import copy
from typing import cast

from atlas import (
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
from atlas.models.business_model import BusinessModel
from atlas.modules.day_ahead_orders.data_models.hydro import HydroDAO
from atlas.modules.day_ahead_orders.data_models.load import LoadDAO
from atlas.modules.day_ahead_orders.data_models.order import OrderDAO
from atlas.modules.day_ahead_orders.data_models.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.data_models.solar import SolarDAO
from atlas.modules.day_ahead_orders.data_models.storage import StorageDAO
from atlas.modules.day_ahead_orders.data_models.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.data_models.wind import WindDAO
from atlas.modules.day_ahead_orders.input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


class DayAheadOrdersOutput(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, input_dataset: DayAheadOrdersInputDataset):
        self.parameters: DayAheadOrdersParameters = copy.deepcopy(input_dataset.parameters)
        self.control_block: list[ControlBlock] = copy.deepcopy(input_dataset.control_block)
        self.market_area: list[MarketArea] = copy.deepcopy(input_dataset.market_area)
        self.market_border: list[MarketBorder] = copy.deepcopy(input_dataset.market_border)
        self.node: list[Node] = copy.deepcopy(input_dataset.node)
        self.portfolio: list[Portfolio] = copy.deepcopy(input_dataset.portfolio)
        self.other_non_dispatchable: list[OtherNonDispatchable] = copy.deepcopy(input_dataset.other_non_dispatchable)

        input_load: list[Load] = copy.deepcopy(input_dataset.load)
        self.load: list[LoadDAO] = [cast(LoadDAO, obj) for obj in input_load]
        input_storage: list[Storage] = copy.deepcopy(input_dataset.storage)
        self.storage: list[StorageDAO] = [cast(StorageDAO, obj) for obj in input_storage]
        input_hydro: list[Hydro] = copy.deepcopy(input_dataset.hydro)
        self.hydro: list[HydroDAO] = [cast(HydroDAO, obj) for obj in input_hydro]
        input_solar: list[Solar] = copy.deepcopy(input_dataset.solar)
        self.solar: list[SolarDAO] = [cast(SolarDAO, obj) for obj in input_solar]
        input_thermal: list[Thermal] = copy.deepcopy(input_dataset.thermal)
        self.thermal: list[ThermalDAO] = [cast(ThermalDAO, obj) for obj in input_thermal]
        input_wind: list[Wind] = copy.deepcopy(input_dataset.wind)
        self.wind: list[WindDAO] = [cast(WindDAO, obj) for obj in input_wind]

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
            OrderDAO,
            OrderCouplingDAO,
        ]
