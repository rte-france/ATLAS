from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.market.market_area import MarketArea


class Portfolio(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    control_block: ControlBlock | None = None
    market_area: MarketArea | None = None
    id_cleared_quantity: ForecastingMatrix | None = None
    imbalance: ForecastingMatrix | None = None
    power: ForecastingMatrix | None = None
    afrr_activated: Timeseries | None = None
    afrr_down_procured: Timeseries | None = None
    afrr_up_procured: Timeseries | None = None
    da_cleared_quantity: Timeseries | None = None
    fcr_activated: Timeseries | None = None
    imbalance_settlement_costs: Timeseries | None = None
    mfrr_activated: Timeseries | None = None
    mfrr_down_procured: Timeseries | None = None
    mfrr_up_procured: Timeseries | None = None
    rr_activated: Timeseries | None = None
    rr_down_procured: Timeseries | None = None
    rr_up_procured: Timeseries | None = None
    total_id_cleared_quantity: Timeseries | None = None
