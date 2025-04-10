from pydantic import BaseModel, ConfigDict

from atlas.config import ComplementDirection, CouplingType
from atlas.models.market.order import Order


class OrderCoupling(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    orders: list[Order]  # List of Business model MarketArea
    complement_direction: ComplementDirection | None = None
    complement_energy: float | None = None
    coupling_type: CouplingType | None = None
