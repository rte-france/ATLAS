"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements BSPBalancingOrdersOutputDataset.
"""

from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling
from atlas.orchestrator.change_set import AddObject


class BSPBalancingOrdersOutputDataset(AbstractModuleOutput[BSPBalancingOrdersParameters]):
    """Output dataset for the Balancing Orders Formulation module.

    Holds the formulated orders and their couplings, ready to be exported
    as change sets to the AtlasDataset.

    To be completed when order formulators are implemented.
    """

    orders: list[Order] = []
    couplings: list[OrderCoupling] = []

    def build_change_sets(self) -> None:
        for order in self.orders:
            self.change_sets.append(AddObject.from_object(order))
        for order_coupling in self.couplings:
            self.change_sets.append(AddObject.from_object(order_coupling))
