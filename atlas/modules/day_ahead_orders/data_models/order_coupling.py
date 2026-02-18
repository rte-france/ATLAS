"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.enums import CouplingType
from atlas.models.market.order import Order
from atlas.models.market.order_coupling import OrderCoupling


class OrderCouplingDAO(OrderCoupling):
    orders: list[Order] = []
    complement_energy: float = 0.0
    coupling_type: CouplingType
