from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.node import Node


class NodePtdf(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    node: Node | None = None
    id_ptdf: ForecastingMatrix | None = None
    da_ptdf: Timeseries | None = None
