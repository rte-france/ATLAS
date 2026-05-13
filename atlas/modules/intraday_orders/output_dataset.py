"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas import Hydro, Load, OrderCoupling, OtherNonDispatchable, Solar, Storage, Thermal, Wind
from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.enums import ThermalStrategy
from atlas.modules.intraday_orders.models.order import IntraDayOrder
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.orchestrator.change_set import AddObject, UpdateObject

if TYPE_CHECKING:
    from atlas.modules.intraday_orders.input_dataset import IntradayOrdersInputDataset


class IntradayOrdersOutputDataset(AbstractModuleOutput[IntradayOrdersParameters]):
    def __init__(self, input_dataset: IntradayOrdersInputDataset):
        self.change_sets = []
        self.order: list[IntraDayOrder] = []
        self.order_coupling: list[OrderCoupling] = []

        self.load: list[Load] = input_dataset.load
        self.hydro: list[Hydro] = input_dataset.hydro
        self.solar: list[Solar] = input_dataset.solar
        self.wind: list[Wind] = input_dataset.wind
        self.thermal: list[Thermal] = input_dataset.thermal
        self.storage: list[Storage] = input_dataset.storage
        self.other_non_dispatchable: list[OtherNonDispatchable] = input_dataset.other_non_dispatchable

    def add_order(self, order: IntraDayOrder) -> None:
        self.order.append(order)

    def add_order_coupling(self, order_coupling: OrderCoupling) -> None:
        self.order_coupling.append(order_coupling)

    def build_change_sets(self):
        for order in self.order:
            self.change_sets.append(AddObject.from_object(order))
        for order_coupling in self.order_coupling:
            self.change_sets.append(AddObject.from_object(order_coupling))

        for load in self.load:
            load_dict = {"name": load.name, "id_buy_submitted_volume": load.id_buy_submitted_volume}
            self.change_sets.append(UpdateObject(load_dict, Load))

        for hydro in self.hydro:
            hydro_dict = {"name": hydro.name, "id_sell_submitted_volume": hydro.id_sell_submitted_volume}
            self.change_sets.append(UpdateObject(hydro_dict, Hydro))

        for solar in self.solar:
            solar_dict = {"name": solar.name, "id_sell_submitted_volume": solar.id_sell_submitted_volume}
            self.change_sets.append(UpdateObject(solar_dict, Solar))

        for wind in self.wind:
            wind_dict = {"name": wind.name, "id_sell_submitted_volume": wind.id_sell_submitted_volume}
            self.change_sets.append(UpdateObject(wind_dict, Wind))

        for other_non_dispatchable in self.other_non_dispatchable:
            other_non_dispatchable_dict = {
                "name": other_non_dispatchable.name,
                "id_sell_submitted_volume": other_non_dispatchable.id_sell_submitted_volume,
            }
            self.change_sets.append(UpdateObject(other_non_dispatchable_dict, OtherNonDispatchable))

        for thermal in self.thermal:
            thermal_dict = {"name": thermal.name, "id_sell_submitted_volume": thermal.id_sell_submitted_volume}
            if thermal.strategy == ThermalStrategy.INTERMEDIATE:
                thermal_dict["state_sequence"] = thermal.state_sequence
            self.change_sets.append(UpdateObject(thermal_dict, Thermal))

        for storage in self.storage:
            storage_dict = {
                "name": storage.name,
                "id_sell_submitted_volume": storage.id_sell_submitted_volume,
                "id_buy_submitted_volume": storage.id_buy_submitted_volume,
                "variable_cost": storage.variable_cost,
            }
            self.change_sets.append(UpdateObject(storage_dict, Storage))
