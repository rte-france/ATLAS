from typing import List


class OrderCoupling:
    orders: List[str] # List of Business model MarketArea
    complement_direction: str # possibles values : EqualTo, GreaterThan, LesserThan
    complement_energy: float
    coupling_type: str # possibles values : EXCLUSION, COMPLEMENT, IDENTICAL_VOLUME, PARENT_CHILDREN, IDENTICAL_RATIO