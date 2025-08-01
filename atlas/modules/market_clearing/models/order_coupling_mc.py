"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import Order
from atlas.enum import ComplementDirection
from atlas.models.market.order_coupling import OrderCoupling


class OrderCouplingMC(OrderCoupling):
    orders: list[Order]
    complement_direction: ComplementDirection
