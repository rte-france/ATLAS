"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BSPBalancingOrdersResult.
"""

from atlas.abstract_class.dataset import ModuleResult
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling
from atlas.orchestrator.change_set import AddObject, ChangeSet


class BSPBalancingOrdersResult(ModuleResult[BSPBalancingOrdersParameters]):
    """Result of the BSP balancing orders module.

    Holds the formulated orders and their couplings, ready to be applied
    as change sets to the AtlasDataset.
    """

    def __init__(self):
        self.change_sets: list[ChangeSet] = []
        self.orders: list[Order] = []
        self.couplings: list[OrderCoupling] = []

    def build_change_sets(self) -> list[ChangeSet]:
        return [
            *(AddObject.from_object(order) for order in self.orders),
            *(AddObject.from_object(order_coupling) for order_coupling in self.couplings),
        ]
