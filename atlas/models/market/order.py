from typing import Literal

from pydantic import BaseModel


class Order(BaseModel):
    equipment: str = None  # Class Business model Equipment
    market_area: str = None  # Class Business model MarketArea
    portfolio: str = None  # Class Business model Portfolio
    accepted_power: float = None
    execution_date: str = None  # Validation for date ?
    start_date: str = None  # Validation for date ?
    end_date: str = None  # Validation for date ?
    individual_spread: float = None
    is_agent_tso: bool = None
    order_type: Literal['Buy', 'Sell'] = None
    price: float = None
    price_group: int = None
    product: Literal['Intraday', 'DayAhead', 'AFRRUpProcurement', 'FRRDownProcurement', 'MFRRUpProcurement',
    'MFRRDownProcurement', 'RRUpProcurement', 'RRDownProcurement', 'AFRRActivation', 'MFRRActivation', 'RRActivation',
    'FCRActivation', 'FCRUpProcurement', 'FCRDownProcurement'] = None
    q_max: float = None
    q_min: float = None
