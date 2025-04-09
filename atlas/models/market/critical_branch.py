from typing import Any


class CriticalBranch:
    downhill_node: str # Class Business model Node
    uphill_node: str # Class Business model Node
    market_area_ptdf: str # Class Business model MarketAreaPtdf
    node_ptdf: str # Class Business model NodePtdf
    id_flow: Any # ForecastMatrix
    id_shadow_price: Any # ForecastMatrix
    da_flow: Any # Timeseries
    da_shadow_price: Any # Timeseries
    flow_reliability_margin: Any # Timeseries
    maximum_flow: Any # Timeseries
    reference_flow: Any # Timeseries
    total_id_flow: Any # Timeseries