"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import field_serializer
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.enums import OrderType, Product
from atlas.objects.business_model import BusinessModel
from atlas.objects.equipment.equipment import Equipment
from atlas.objects.market.market_area import MarketArea
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.validators import serializer_business_model


class Order(BusinessModel):
    """:param equipment: Associated Equipment
    :type equipment: Equipment
    :param market_area: Associated Market Area
    :type market_area: Market Area
    :param portfolio: Associated Portfolio
    :type portfolio: Portfolio
    :param accepted_power: Accepted power after Clearing
    :type accepted_power: float
    :param execution_date: Date of offer
    :type execution_date: DateTime
    :param start_date: Offer activation start DateTime
    :type start_date: DateTime
    :param end_date: Offer activation end DateTime
    :type end_date: DateTime
    :param individual_spread: "Profit (in the sense of social welfare) of the offer :
        _ spot price - offer price for a sell offer
        _ offer price - spot price for a purchase offer
        This difference is then multiplied by the power sold/purchased"
    :type individual_spread: float
    :param is_agent_tso: True if Agent is TSO, False otherwise
    :type is_agent_tso: bool
    :param order_type: Order type (Buy, Sell)
    :type order_type: OrderType
    :param price: Price of the offer
    :type price: float
    :param price_group: Price group containing the offer, after Clearing
    :type price_group: int
    :param product: Type of product
    :type product: Product
    :param q_max: Maximum quantity that can be accepted in the clearing phase
    :type q_max: float
    :param q_min: Minimum quantity that can be accepted in the clearing phase
    :type q_min: float
    """

    equipment: Equipment | None = None
    market_area: MarketArea
    portfolio: Portfolio | None = None
    accepted_power: float | None = None
    execution_date: DateTime | None = None
    start_date: DateTime | None = None
    end_date: DateTime | None = None
    individual_spread: float | None = None
    is_agent_tso: bool | None = None
    order_type: OrderType | None = None
    price: float | None = None
    price_group: int | None = None
    product: Product | None = None
    qmax: float | None = None
    qmin: float | None = None

    @field_serializer("equipment", "market_area", "portfolio", mode="plain")
    def serializer_bmo(self, value: BusinessModel | None) -> str | None:
        """Serialize BusinessModel attributes to string."""
        return serializer_business_model(value)
