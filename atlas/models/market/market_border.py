from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.market.market_area import MarketArea


class MarketBorder(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    downhill_control_block: ControlBlock | None = None
    uphill_control_block: ControlBlock | None = None
    downhill_market_area: MarketArea | None = None
    uphill_market_area: MarketArea | None = None
    coupling_type: str | None = None
    loss_factor: float | None = None
    time_resolution: float | None = None  # Assuming this can be a float
    afrr_down_procured: ForecastingMatrix | None = None
    afrr_up_procured: ForecastingMatrix | None = None
    id_flow: ForecastingMatrix | None = None
    id_shadow_price: ForecastingMatrix | None = None
    mfrr_down_procured: ForecastingMatrix | None = None
    mfrr_up_procured: ForecastingMatrix | None = None
    rr_down_procured: ForecastingMatrix | None = None
    rr_up_procured: ForecastingMatrix | None = None
    afrr_activated: Timeseries | None = None
    da_flow: Timeseries | None = None
    da_shadow_price: Timeseries | None = None
    fcr_activated: Timeseries | None = None
    maximum_flow: Timeseries | None = None
    mfrr_activated: Timeseries | None = None
    minimum_flow: Timeseries | None = None
    reference_flow: Timeseries | None = None
    rr_activated: Timeseries | None = None
    total_id_flow: Timeseries | None = None
