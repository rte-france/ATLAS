from typing import Any

from pydantic import BaseModel


class Node(BaseModel):
    control_block: str = None  # Class Business model ControlBlock
    market_area: str = None  # Class Business model MarketArea
    balance_forecast: Any = None  # ForecastMatrix
    id_power_injection: Any = None  # ForecastMatrix
    da_power_injection: Any = None  # Timeseries
    reference_balance: Any = None  # Timeseries
