from atlas.models.equipment.equipment import Equipment
from atlas.models.market.order import Order


class OrderDAO(Order):
    equipment: Equipment
    # market_area: MarketArea | None = None
    # portfolio: Portfolio | None = None
    # accepted_power: float | None = None
    # execution_date: DateTime | None = None
    # start_date: DateTime | None = None
    # end_date: DateTime | None = None
    # individual_spread: float | None = None
    # is_agent_tso: bool | None = None
    # order_type: OrderType | None = None
    # price: float | None = None
    # price_group: int | None = None
    # product: Product | None = None
    # qmax: float | None = None
    # qmin: float | None = None
