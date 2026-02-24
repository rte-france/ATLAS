"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pendulum import Duration

from atlas import AtlasDataset
from atlas.config import EQUIPMENT_MODELS
from atlas.enums import StorageType


class UpdateDataset:
    def __init__(self, atlas_dataset: AtlasDataset):
        self.atlas_dataset = atlas_dataset

    def standard_update(self):
        self.add_equipments_default_values()
        self.add_storages_default_values()
        self.add_market_borders_default_values()

    def add_equipments_default_values(self):
        for equipment_name in EQUIPMENT_MODELS:
            for equipment in self.atlas_dataset.get_container_by_type(equipment_name):
                equipment.maximum_afrr = 0 if equipment.maximum_afrr is None else equipment.maximum_afrr
                equipment.maximum_fcr = 0 if equipment.maximum_fcr is None else equipment.maximum_fcr
                equipment.setup_delay = 0 if equipment.setup_delay is None else equipment.setup_delay
                equipment.unit_count = 1 if equipment.unit_count is None else equipment.unit_count
                equipment.maximum_gradient = 0 if equipment.maximum_gradient is None else equipment.maximum_gradient

    def add_storages_default_values(self):
        for storage in self.atlas_dataset.storage:
            storage.transition_duration = (
                pendulum.Duration(hours=1) if storage.transition_duration is None else storage.transition_duration
            )

            if storage.additional_hours_ is None:
                if storage.storage_type == StorageType.PUMPED_HYDRAULIC_STORAGE:
                    storage.additional_hours_ = Duration(hours=144)
                elif storage.storage_type == StorageType.BATTERY:
                    storage.additional_hours_ = Duration(hours=48)
                elif storage.storage_type == StorageType.ELECTRIC_VEHICLE:
                    storage.additional_hours_ = Duration(hours=24)
                else:
                    storage.additional_hours_ = Duration(hours=48)

    def add_market_borders_default_values(self):
        for market_border in self.atlas_dataset.market_border:
            market_border.coupling_type = "ATC" if market_border.coupling_type is None else market_border.coupling_type
            market_border.time_resolution = (
                0.0 if market_border.time_resolution is None else market_border.time_resolution
            )
