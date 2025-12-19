"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.models.equipment.equipment import Equipment
from atlas.models.market.order import Order


class OrderDAO(Order):
    equipment: Equipment
