"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.enums import CouplingType
from atlas.objects.market.order_coupling import OrderCoupling


class OrderCouplingMC(OrderCoupling):
    coupling_type: CouplingType
