from datetime import date

from pydantic import BaseModel

from atlas.config import OrderType, Product
from atlas.models.equipment.equipment import Equipment
from atlas.models.market.market_area import MarketArea
from atlas.models.portfolio import Portfolio


class Order(BaseModel):
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
