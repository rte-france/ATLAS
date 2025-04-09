from typing import List, Literal

from pydantic import BaseModel


class OrderCoupling(BaseModel):
    orders: List[str]  # List of Business model MarketArea
    complement_direction: Literal['EqualTo', 'GreaterThan', 'LesserThan'] = None
    complement_energy: float = None
    coupling_type: Literal['EXCLUSION', 'COMPLEMENT', 'IDENTICAL_VOLUME', 'PARENT_CHILDREN', 'IDENTICAL_RATIO'] = None
