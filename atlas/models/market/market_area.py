from typing import Any


class MarketArea:
    control_block: str # Class Business model ControlBlock
    co2_emission: Any # ForecastMatrix
    id_balance: Any # ForecastMatrix
    id_price: Any # ForecastMatrix
    id_price_forecast: Any # ForecastMatrix
    price_forecast_high: Any # ForecastMatrix
    price_forecast_low: Any # ForecastMatrix
    price_forecast_medium: Any # ForecastMatrix
    afrr_activation_price: Any # Timeseries
    da_balance: Any # Timeseries
    fcr_activation_price: Any # Timeseries
    maximum_price: Any # Timeseries
    mfrr_activation_balance: Any # Timeseries
    mfrr_activation_price: Any # Timeseries
    minimum_price: Any # Timeseries
    reference_balance: Any # Timeseries
    rr_activation_balance: Any # Timeseries
    rr_activation_price: Any # Timeseries
    total_id_balance: Any # Timeseries