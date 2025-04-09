from typing import Any

from pydantic import BaseModel


class CriticalBranch(BaseModel):
    downhill_node: str = None  # Class Business model Node
    uphill_node: str = None  # Class Business model Node
    market_area_ptdf: str = None  # Class Business model MarketAreaPtdf
    node_ptdf: str = None  # Class Business model NodePtdf
    id_flow: Any = None  # ForecastMatrix
    id_shadow_price: Any = None  # ForecastMatrix
    da_flow: Any = None  # Timeseries
    da_shadow_price: Any = None  # Timeseries
    flow_reliability_margin: Any = None  # Timeseries
    maximum_flow: Any = None  # Timeseries
    reference_flow: Any = None  # Timeseries
    total_id_flow: Any = None  # Timeseries
