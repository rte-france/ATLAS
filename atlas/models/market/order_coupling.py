"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.config import ComplementDirection, CouplingType
from atlas.models.business_model import BusinessModel
from atlas.models.market.order import Order


class OrderCoupling(BusinessModel):
    """:param orders: List of Order linked
    :type orders: list[Order]
    :param complement_direction: Complement coupling constraint direction (EqualTo, LesserThan, GreaterThan)
    :type complement_direction: ComplementDirection
    :param complement_energy: Target energy for complement offers
    :type complement_energy: float
    :param coupling_type: Offer type (EXCLUSION, COMPLEMENT, IDENTICAL_VOLUME, PARENT_CHILDREN)
    :type coupling_type: CouplingType
    """

    orders: list[Order]  # List of Business model Order
    complement_direction: ComplementDirection | None = None
    complement_energy: float | None = None
    coupling_type: CouplingType | None = None
