from atlas import MarketArea, AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries


class MarketAreaIDPF(MarketArea):
    price_forecast_low: ForecastingMatrix | LazyForecastingMatrix
    price_forecast_high: ForecastingMatrix | LazyForecastingMatrix
    id_price: ForecastingMatrix
    da_price: AbstractTimeseries
    id_price_forecast: ForecastingMatrix
