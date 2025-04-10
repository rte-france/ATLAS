from pydantic import BaseModel

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock


class Node(BaseModel):
    control_block: ControlBlock | None = None
    market_area: str | None = None
    balance_forecast: ForecastingMatrix | None = None
    id_power_injection: ForecastingMatrix | None = None
    da_power_injection: Timeseries | None = None
    reference_balance: Timeseries | None = None
