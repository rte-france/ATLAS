from typing import Any

from pydantic import BaseModel


class MarketAreaPtdf(BaseModel):
    market_area: str = None  # Class Business model MarketArea
    id_ptdf: Any = None  # ForecastMatrix
    da_ptdf: Any = None  # Timeseries
