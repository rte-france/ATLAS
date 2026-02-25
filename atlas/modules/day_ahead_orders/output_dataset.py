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
    OtherNonDispatchable,
    Portfolio,
    Solar,
    Storage,
    Thermal,
    Wind,
)
from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.enums import ThermalStrategy
from atlas.models.business_model import BusinessModel
from atlas.modules.day_ahead_orders.data_models.hydro import HydroDAO
from atlas.modules.day_ahead_orders.data_models.load import LoadDAO
from atlas.modules.day_ahead_orders.data_models.market_area import MarketAreaDAO
from atlas.modules.day_ahead_orders.data_models.order import OrderDAO
from atlas.modules.day_ahead_orders.data_models.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.data_models.portfolio import PortfolioDAO
from atlas.modules.day_ahead_orders.data_models.solar import SolarDAO
from atlas.modules.day_ahead_orders.data_models.storage import StorageDAO
from atlas.modules.day_ahead_orders.data_models.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.data_models.wind import WindDAO
from atlas.modules.day_ahead_orders.input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.workflow.change_set import AddObject, UpdateObject


class DayAheadOrdersOutput(AbstractModuleOutput[DayAheadOrdersParameters]):
    def __init__(self, input_dataset: DayAheadOrdersInputDataset):
        super().__init__()
        self.parameters: DayAheadOrdersParameters = copy.deepcopy(input_dataset.parameters)
        self.control_block: list[ControlBlock] = copy.deepcopy(input_dataset.control_block)
        self.market_area: list[MarketAreaDAO] = copy.deepcopy(input_dataset.market_area)
        self.portfolio: list[PortfolioDAO] = copy.deepcopy(input_dataset.portfolio)
        self.other_non_dispatchable: list[OtherNonDispatchable] = copy.deepcopy(input_dataset.other_non_dispatchable)

        self.load: list[LoadDAO] = copy.deepcopy(input_dataset.load)
        self.storage: list[StorageDAO] = copy.deepcopy(input_dataset.storage)
        self.hydro: list[HydroDAO] = copy.deepcopy(input_dataset.hydro)
        self.solar: list[SolarDAO] = copy.deepcopy(input_dataset.solar)
        self.thermal: list[ThermalDAO] = copy.deepcopy(input_dataset.thermal)
        self.wind: list[WindDAO] = copy.deepcopy(input_dataset.wind)

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

    def build_change_sets(self):
        for order in self.order:
            self.change_sets.append(AddObject.from_object(order))
        for order_coupling in self.order_coupling:
            self.change_sets.append(AddObject.from_object(order_coupling))

        for load in self.load:
            load_dict = {"name": load.name, "da_buy_submitted_volume": load.da_buy_submitted_volume}
            self.change_sets.append(UpdateObject(load_dict, Load))

        for hydro in self.hydro:
            hydro_dict = {"name": hydro.name, "da_sell_submitted_volume": hydro.da_sell_submitted_volume}
            self.change_sets.append(UpdateObject(hydro_dict, Hydro))

        for solar in self.solar:
            solar_dict = {"name": solar.name, "da_sell_submitted_volume": solar.da_sell_submitted_volume}
            self.change_sets.append(UpdateObject(solar_dict, Solar))

        for wind in self.wind:
            wind_dict = {"name": wind.name, "da_sell_submitted_volume": wind.da_sell_submitted_volume}
            self.change_sets.append(UpdateObject(wind_dict, Wind))

        for other_non_dispatchable in self.other_non_dispatchable:
            other_non_dispatchable_dict = {
                "name": other_non_dispatchable.name,
                "da_sell_submitted_volume": other_non_dispatchable.da_sell_submitted_volume,
            }
            self.change_sets.append(UpdateObject(other_non_dispatchable_dict, OtherNonDispatchable))

        for thermal in self.thermal:
            thermal_dict = {"name": thermal.name, "da_sell_submitted_volume": thermal.da_sell_submitted_volume}
            if thermal.strategy == ThermalStrategy.INTERMEDIATE:
                thermal_dict["state_sequence"] = thermal.state_sequence
            self.change_sets.append(UpdateObject(thermal_dict, Thermal))

        for storage in self.storage:
            storage_dict = {
                "name": storage.name,
                "da_sell_submitted_volume": storage.da_sell_submitted_volume,
                "da_buy_submitted_volume": storage.da_buy_submitted_volume,
                "variable_cost": storage.variable_cost,
            }
            self.change_sets.append(UpdateObject(storage_dict, Storage))
