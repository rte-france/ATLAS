from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries


class MarketAreaPtdf(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    market_area: str | None = None
    id_ptdf: ForecastingMatrix | None = None
    da_ptdf: Timeseries | None = None
