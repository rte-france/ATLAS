"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import field_serializer

from atlas.enums import ComplementDirection, CouplingType
from atlas.models.business_model import BusinessModel
from atlas.models.market.order import Order
from atlas.validators import serializer_list_business_model


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

    orders: list[Order] | None = None
    complement_direction: ComplementDirection | None = None
    complement_energy: float | None = None
    coupling_type: CouplingType | None = None

    @field_serializer("orders", mode="plain")
    def serializer_orders(self, value: list[BusinessModel] | None) -> str | None:
        return serializer_list_business_model(value)
