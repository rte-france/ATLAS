from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries


class CriticalBranch(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    downhill_node: str | None = None
    uphill_node: str | None = None
    market_area_ptdf: str | None = None
    node_ptdf: str | None = None
    id_flow: ForecastingMatrix | None = None
    id_shadow_price: ForecastingMatrix | None = None
    da_flow: Timeseries | None = None
    da_shadow_price: Timeseries | None = None
    flow_reliability_margin: Timeseries | None = None
    maximum_flow: Timeseries | None = None
    reference_flow: Timeseries | None = None
    total_id_flow: Timeseries | None = None
