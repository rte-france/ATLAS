"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import OtherNonDispatchable
from atlas.abstract_class.dataset import ModuleResult
from atlas.modules.price_forecast_orders_creation.input_dataset import PriceForecastOrdersCreationInputDataset
from atlas.modules.price_forecast_orders_creation.input_objects.hydro import HydroPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.load import LoadPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.order import OrderPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.order_coupling import OrderCouplingPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.storage import StoragePFOC
from atlas.modules.price_forecast_orders_creation.input_objects.thermal import ThermalPFOC
from atlas.modules.price_forecast_orders_creation.input_objects.wind import WindPFOC
from atlas.modules.price_forecast_orders_creation.parameters import PriceForecastOrdersCreationParameters
from atlas.orchestrator.change_set import ChangeSet


class PriceForecastOrdersCreationResult(ModuleResult[PriceForecastOrdersCreationParameters]):
    def __init__(self, input_dataset: PriceForecastOrdersCreationInputDataset):
        self.parameters: PriceForecastOrdersCreationParameters = input_dataset.parameters

        self.other_non_dispatchable: list[OtherNonDispatchable] = input_dataset.other_non_dispatchable
        self.storage: list[StoragePFOC] = input_dataset.storage
        self.hydro: list[HydroPFOC] = input_dataset.hydro
        self.wind: list[WindPFOC] = input_dataset.wind
        self.solar: list[SolarPFOC] = input_dataset.solar
        self.thermal: list[ThermalPFOC] = input_dataset.thermal
        self.load: list[LoadPFOC] = input_dataset.load

        self.order: list[OrderPFOC] = []
        self.order_coupling: list[OrderCouplingPFOC] = []

    def build_change_sets(self) -> list[ChangeSet]:
        pass
