"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class DayAheadOrdersOutputDataset(AbstractDataset[DayAheadOrdersParameters]):
    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []
