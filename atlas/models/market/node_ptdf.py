from pydantic import BaseModel

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.node import Node


class MarketAreaPtdf(BaseModel):
    node: Node | None = None  # Class Business model Node
    id_ptdf: ForecastingMatrix | None = None
    da_ptdf: Timeseries | None = None
