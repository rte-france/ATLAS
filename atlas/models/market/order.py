"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import date

from pydantic import BaseModel

from atlas.config import OrderType, Product
from atlas.models.equipment.equipment import Equipment
from atlas.models.market.market_area import MarketArea
from atlas.models.portfolio import Portfolio


class Order(BaseModel):
    """:param equipment: Associated Equipment
    :type equipment: Equipment
    :param market_area: Associated Market Area
    :type market_area: Market Area
    :param portfolio: Associated Portfolio
    :type portfolio: Portfolio
    :param accepted_power: Accepted power after Clearing
    :type accepted_power: float
    :param execution_date: Date of offer
    :type execution_date: date
    :param start_date: Offer activation start date
    :type start_date: date
    :param end_date: Offer activation end date
    :type end_date: date
    :param individual_spread: "Profit (in the sense of social welfare) of the offer :
        _ spot price - offer price for a sell offer
        _ offer price - spot price for a purchase offer
        This difference is then multiplied by the power sold/purchased"
    :type individual_spread: float
    :param is_agent_tso: True of Agent is TSO, False otherwise
    :type is_agent_tso: bool
    :param order_type: Order type (Buy, Sell)
    :type order_type: OrderType
    :param price: Price of the offer
    :type price: float
    :param price_group: Price group containing the offer, after Clearing
    :type price_group: int
    :param product: Type of product
    :type product: Product
    :param q_max: Maximum bid volume that can be accepted in the clearing phase
    :type q_max: float
    :param q_min: Minimum bid volume that can be accepted in the clearing phase
    :type q_min: float
    """

    equipment: Equipment | None = None
    market_area: MarketArea | None = None
    portfolio: Portfolio | None = None  # Class Business model Portfolio
    accepted_power: float | None = None
    execution_date: date | None = None  # Validating date using Pydantic's date type
    start_date: date | None = None  # Validating date using Pydantic's date type
    end_date: date | None = None  # Validating date using Pydantic's date type
    individual_spread: float | None = None
    is_agent_tso: bool | None = None
    order_type: OrderType | None = None
    price: float | None = None
    price_group: int | None = None
    product: Product | None = None
    q_max: float | None = None
    q_min: float | None = None
