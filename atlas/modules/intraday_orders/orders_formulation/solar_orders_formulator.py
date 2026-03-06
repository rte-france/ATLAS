"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import List

from pendulum import DateTime

from atlas import Solar
from atlas.modules.intraday_orders.orders_formulation.abstract_orders_formulator_with_curtailment import (
    AbstractOrdersFormulatorWithCurtailment,
)
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import intraday_step


class SolarOrdersFormulator(AbstractOrdersFormulatorWithCurtailment[Solar]):
    ORDER_NAME_TEMPLATE = "pv_IDOrder_{}_{}_{}"
    CURTAILMENT_ORDER_NAME_TEMPLATE = "pv_curt_IDOrder_{}_{}_{}"

    @intraday_step("solar")
    def formulate_orders(
        self,
        equipments: List[Solar],
        orders_timestamps: List[DateTime],
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        super().formulate_orders(equipments, orders_timestamps, dataset, parameters)
