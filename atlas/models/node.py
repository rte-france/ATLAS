from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.market.market_area import MarketArea


class Node(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    control_block: ControlBlock | None = None
    market_area: MarketArea | None = None
    balance_forecast: ForecastingMatrix | None = None
    id_power_injection: ForecastingMatrix | None = None
    da_power_injection: Timeseries | None = None
    reference_balance: Timeseries | None = None
