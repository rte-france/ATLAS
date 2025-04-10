from pydantic import BaseModel

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries


class MarketAreaPtdf(BaseModel):
    market_area: str | None = None
    id_ptdf: ForecastingMatrix | None = None
    da_ptdf: Timeseries | None = None
