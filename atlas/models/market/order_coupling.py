from pydantic import BaseModel

from atlas.config import ComplementDirection, CouplingType


class OrderCoupling(BaseModel):
    orders: list[str]  # List of Business model MarketArea
    complement_direction: ComplementDirection | None = None
    complement_energy: float | None = None
    coupling_type: CouplingType | None = None
