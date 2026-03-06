"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import List

from pendulum import DateTime

from atlas import Storage
from atlas.modules.intraday_orders.orders_formulation.abstract_orders_formulator import AbstractOrdersFormulator
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import intraday_step


class StorageOrdersFormulator(AbstractOrdersFormulator[Storage]):
    @intraday_step("storage")
    def formulate_orders(
        self,
        equipments: List[Storage],
        orders_timestamps: List[DateTime],
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        # TODO
        pass
