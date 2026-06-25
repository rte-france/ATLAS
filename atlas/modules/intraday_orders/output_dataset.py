"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.enums import ThermalStrategy
from atlas.modules.intraday_orders.input_objects.hydro import HydroIDO
from atlas.modules.intraday_orders.input_objects.load import LoadIDO
from atlas.modules.intraday_orders.input_objects.other_non_dispatchable import OtherNonDispatchableIDO
from atlas.modules.intraday_orders.input_objects.solar import SolarIDO
from atlas.modules.intraday_orders.input_objects.storage import StorageIDO
from atlas.modules.intraday_orders.input_objects.thermal import ThermalIDO
from atlas.modules.intraday_orders.input_objects.wind import WindIDO
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.objects.equipment.hydro import Hydro
from atlas.objects.equipment.load import Load
from atlas.objects.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.objects.equipment.solar import Solar
from atlas.objects.equipment.storage import Storage
from atlas.objects.equipment.thermal import Thermal
from atlas.objects.equipment.wind import Wind
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling
from atlas.orchestrator.change_set import AddObject, UpdateObject

if TYPE_CHECKING:
    from atlas.modules.intraday_orders.input_dataset import IntradayOrdersInputDataset


class IntradayOrdersOutputDataset(AbstractModuleOutput[IntradayOrdersParameters]):
    def __init__(self, input_dataset: IntradayOrdersInputDataset):
        self.change_sets = []
        self.order: list[Order] = []
        self.order_coupling: list[OrderCoupling] = []

        self.load: list[LoadIDO] = input_dataset.load
        self.hydro: list[HydroIDO] = input_dataset.hydro
        self.solar: list[SolarIDO] = input_dataset.solar
        self.wind: list[WindIDO] = input_dataset.wind
        self.thermal: list[ThermalIDO] = input_dataset.thermal
        self.storage: list[StorageIDO] = input_dataset.storage
        self.other_non_dispatchable: list[OtherNonDispatchableIDO] = input_dataset.other_non_dispatchable

    def build_change_sets(self):
        for order in self.order:
            self.change_sets.append(AddObject.from_object(order))
        for order_coupling in self.order_coupling:
            self.change_sets.append(AddObject.from_object(order_coupling))

        for load in self.load:
            load_dict = {
                "name": load.name,
                "id_sell_submitted_volume": load.id_sell_submitted_volume,
                "id_buy_submitted_volume": load.id_buy_submitted_volume,
                "total_id_buy_submitted_volume": load.total_id_buy_submitted_volume,
                "total_id_sell_submitted_volume": load.total_id_sell_submitted_volume,
            }
            self.change_sets.append(UpdateObject(load_dict, Load))

        for hydro in self.hydro:
            hydro_dict = {
                "name": hydro.name,
                "id_sell_submitted_volume": hydro.id_sell_submitted_volume,
                "id_buy_submitted_volume": hydro.id_buy_submitted_volume,
                "total_id_buy_submitted_volume": hydro.total_id_buy_submitted_volume,
                "total_id_sell_submitted_volume": hydro.total_id_sell_submitted_volume,
            }
            self.change_sets.append(UpdateObject(hydro_dict, Hydro))

        for solar in self.solar:
            solar_dict = {
                "name": solar.name,
                "id_sell_submitted_volume": solar.id_sell_submitted_volume,
                "id_buy_submitted_volume": solar.id_buy_submitted_volume,
                "total_id_buy_submitted_volume": solar.total_id_buy_submitted_volume,
                "total_id_sell_submitted_volume": solar.total_id_sell_submitted_volume,
            }
            self.change_sets.append(UpdateObject(solar_dict, Solar))

        for wind in self.wind:
            wind_dict = {
                "name": wind.name,
                "id_sell_submitted_volume": wind.id_sell_submitted_volume,
                "id_buy_submitted_volume": wind.id_buy_submitted_volume,
                "total_id_buy_submitted_volume": wind.total_id_buy_submitted_volume,
                "total_id_sell_submitted_volume": wind.total_id_sell_submitted_volume,
            }
            self.change_sets.append(UpdateObject(wind_dict, Wind))

        for other_non_dispatchable in self.other_non_dispatchable:
            other_non_dispatchable_dict = {
                "name": other_non_dispatchable.name,
                "id_sell_submitted_volume": other_non_dispatchable.id_sell_submitted_volume,
                "id_buy_submitted_volume": other_non_dispatchable.id_buy_submitted_volume,
                "total_id_buy_submitted_volume": other_non_dispatchable.total_id_buy_submitted_volume,
                "total_id_sell_submitted_volume": other_non_dispatchable.total_id_sell_submitted_volume,
            }
            self.change_sets.append(UpdateObject(other_non_dispatchable_dict, OtherNonDispatchable))

        for thermal in self.thermal:
            thermal_dict: dict[str, Any] = {
                "name": thermal.name,
                "id_sell_submitted_volume": thermal.id_sell_submitted_volume,
                "id_buy_submitted_volume": thermal.id_buy_submitted_volume,
                "total_id_buy_submitted_volume": thermal.total_id_buy_submitted_volume,
                "total_id_sell_submitted_volume": thermal.total_id_sell_submitted_volume,
            }
            if thermal.strategy == ThermalStrategy.INTERMEDIATE:
                thermal_dict["state_sequence"] = thermal.state_sequence
            self.change_sets.append(UpdateObject(thermal_dict, Thermal))

        for storage in self.storage:
            storage_dict = {
                "name": storage.name,
                "id_sell_submitted_volume": storage.id_sell_submitted_volume,
                "id_buy_submitted_volume": storage.id_buy_submitted_volume,
            }
            self.change_sets.append(UpdateObject(storage_dict, Storage))
