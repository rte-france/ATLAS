"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import Load, Hydro, Solar, Wind, OtherNonDispatchable, Thermal, Storage, OrderCoupling
from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.enums import ThermalStrategy
from atlas.modules.intraday_orders.models.order import IntraDayOrder
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.workflow.change_set import AddObject, UpdateObject


class IntradayOrdersOutputDataset(AbstractModuleOutput[IntradayOrdersParameters]):
    def __init__(self):
        super().__init__()
        self.__orders: list[IntraDayOrder] = []
        self.__order_couplings: list[OrderCoupling] = []

    def add_order(self, order: IntraDayOrder) -> None:
        self.__orders.append(order)

    def get_orders(self) -> list[IntraDayOrder]:
        return self.__orders[:]

    def add_order_coupling(self, order_coupling: OrderCoupling) -> None:
        self.__order_couplings.append(order_coupling)

    def get_order_couplings(self) -> list[OrderCoupling]:
        return self.__order_couplings[:]

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
