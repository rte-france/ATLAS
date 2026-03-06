"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.modules.intraday_orders.models.order import IntraDayOrder
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters


class IntradayOrdersOutputDataset(AbstractModuleOutput[IntradayOrdersParameters]):
    def __init__(self):
        super().__init__()
        self.__orders: list[IntraDayOrder] = []

    def add_order(self, order: IntraDayOrder) -> None:
        self.__orders.append(order)

    def get_orders(self) -> list[IntraDayOrder]:
        return self.__orders[:]

    def build_change_sets(self) -> None:
        pass
