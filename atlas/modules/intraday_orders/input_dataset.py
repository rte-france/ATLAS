"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import AtlasDataset
from atlas.abstract_class.dataset import AbstractDataset
from atlas.modules.intraday_orders.input_objects.hydro import HydroIDO
from atlas.modules.intraday_orders.input_objects.load import LoadIDO
from atlas.modules.intraday_orders.input_objects.other_non_dispatchable import OtherNonDispatchableIDO
from atlas.modules.intraday_orders.input_objects.solar import SolarIDO
from atlas.modules.intraday_orders.input_objects.storage import StorageIDO
from atlas.modules.intraday_orders.input_objects.thermal import ThermalIDO
from atlas.modules.intraday_orders.input_objects.wind import WindIDO
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters


class IntradayOrdersInputDataset(AbstractDataset[IntradayOrdersParameters]):
    def __init__(self, input_dataset: AtlasDataset):
        self.hydro: list[HydroIDO] = [HydroIDO(**dict(obj)) for obj in input_dataset.hydro]
        self.load: list[LoadIDO] = [LoadIDO(**dict(obj)) for obj in input_dataset.load]
        self.other_non_dispatchable: list[OtherNonDispatchableIDO] = [
            OtherNonDispatchableIDO(**dict(obj)) for obj in input_dataset.other_non_dispatchable
        ]
        self.solar: list[SolarIDO] = [SolarIDO(**dict(obj)) for obj in input_dataset.solar]
        self.storage: list[StorageIDO] = [StorageIDO(**dict(obj)) for obj in input_dataset.storage]
        self.thermal: list[ThermalIDO] = [ThermalIDO(**dict(obj)) for obj in input_dataset.thermal]
        self.wind: list[WindIDO] = [WindIDO(**dict(obj)) for obj in input_dataset.wind]
