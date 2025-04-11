from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock


class MarketArea(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    control_block: ControlBlock | None = None
    co2_emission: ForecastingMatrix | None = None
    id_balance: ForecastingMatrix | None = None
    id_price: ForecastingMatrix | None = None
    id_price_forecast: ForecastingMatrix | None = None
    price_forecast_high: ForecastingMatrix | None = None
    price_forecast_low: ForecastingMatrix | None = None
    price_forecast_medium: ForecastingMatrix | None = None
    afrr_activation_price: Timeseries | None = None
    da_balance: Timeseries | None = None
    fcr_activation_price: Timeseries | None = None
    maximum_price: Timeseries | None = None
    mfrr_activation_balance: Timeseries | None = None
    mfrr_activation_price: Timeseries | None = None
    minimum_price: Timeseries | None = None
    reference_balance: Timeseries | None = None
    rr_activation_balance: Timeseries | None = None
    rr_activation_price: Timeseries | None = None
    total_id_balance: Timeseries | None = None
