from typing import Any

from pydantic import BaseModel


class MarketAreaPtdf(BaseModel):
    node: str = None  # Class Business model Node
    id_ptdf: Any = None  # ForecastMatrix
    da_ptdf: Any = None  # Timeseries
