"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.enum import CouplingType
from atlas.models.market.order_coupling import OrderCoupling
from atlas.modules.day_ahead_orders.orders_formulation.models.order import OrderDAO


class OrderCouplingDAO(OrderCoupling):
    orders: list[OrderDAO] = []
    complement_energy: float = 0.0
    coupling_type: CouplingType
