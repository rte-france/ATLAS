"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List

from pendulum import DateTime

from atlas import Equipment
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters

E = TypeVar("E", bound=Equipment)


class AbstractOrdersFormulator(ABC, Generic[E]):
    @abstractmethod
    def formulate_orders(
        self,
        equipments: List[E],
        orders_timestamps: List[DateTime],
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        """TODO"""
        raise NotImplementedError()
