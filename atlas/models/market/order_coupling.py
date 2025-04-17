"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import BaseModel, ConfigDict

from atlas.config import ComplementDirection, CouplingType
from atlas.models.market.order import Order


class OrderCoupling(BaseModel):
    """:param orders: List of Order linked
    :type orders: list[Order]
    :param complement_direction: Complement direction (EqualTo, LesserThan, GreaterThan)
    :type complement_direction: ComplementDirection
    :param complement_energy: Target energy for complement offers
    :type complement_energy: float
    :param coupling_type: Offer type (EXCLUSION, COMPLEMENT, IDENTICAL_VOLUME, PARENT_CHILDREN)
    :type coupling_type: CouplingType
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    orders: list[Order]  # List of Business model Order
    complement_direction: ComplementDirection | None = None
    complement_energy: float | None = None
    coupling_type: CouplingType | None = None
