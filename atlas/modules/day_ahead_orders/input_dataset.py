"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import TypeVar

from atlas.abstract_class.dataset import AbstractDataset
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.day_ahead_orders.input_objects.hydro import HydroDAO
from atlas.modules.day_ahead_orders.input_objects.load import LoadDAO
from atlas.modules.day_ahead_orders.input_objects.solar import SolarDAO
from atlas.modules.day_ahead_orders.input_objects.storage import StorageDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.input_objects.wind import WindDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.objects.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.objects.network_operator.control_block import ControlBlock

T = TypeVar("T")


class DayAheadOrdersInputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def __init__(self, input_data: AtlasDataset, parameters: DayAheadOrdersParameters):
        self.parameters: DayAheadOrdersParameters = parameters
        self.control_block: list[ControlBlock] = input_data.control_block.all()
        self.other_non_dispatchable: list[OtherNonDispatchable] = input_data.other_non_dispatchable.all()

        self.wind: list[WindDAO] = [WindDAO(**dict(obj)) for obj in input_data.wind]
        self.storage: list[StorageDAO] = [StorageDAO(**dict(obj)) for obj in input_data.storage]
        self.hydro: list[HydroDAO] = [HydroDAO(**dict(obj)) for obj in input_data.hydro]
        self.solar: list[SolarDAO] = [SolarDAO(**dict(obj)) for obj in input_data.solar]
        self.thermal: list[ThermalDAO] = [ThermalDAO(**dict(obj)) for obj in input_data.thermal]
        self.load: list[LoadDAO] = [LoadDAO(**dict(obj)) for obj in input_data.load]
