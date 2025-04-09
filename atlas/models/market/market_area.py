from typing import Any

from pydantic import BaseModel


class MarketArea(BaseModel):
    control_block: str = None  # Class Business model ControlBlock
    co2_emission: Any = None  # ForecastMatrix
    id_balance: Any = None  # ForecastMatrix
    id_price: Any = None  # ForecastMatrix
    id_price_forecast: Any = None  # ForecastMatrix
    price_forecast_high: Any = None  # ForecastMatrix
    price_forecast_low: Any = None  # ForecastMatrix
    price_forecast_medium: Any = None  # ForecastMatrix
    afrr_activation_price: Any = None  # Timeseries
    da_balance: Any = None  # Timeseries
    fcr_activation_price: Any = None  # Timeseries
    maximum_price: Any = None  # Timeseries
    mfrr_activation_balance: Any = None  # Timeseries
    mfrr_activation_price: Any = None  # Timeseries
    minimum_price: Any = None  # Timeseries
    reference_balance: Any = None  # Timeseries
    rr_activation_balance: Any = None  # Timeseries
    rr_activation_price: Any = None  # Timeseries
    total_id_balance: Any = None  # Timeseries
