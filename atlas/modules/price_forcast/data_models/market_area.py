from atlas import MarketArea
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries


class MarketAreaIDPF(MarketArea):
    price_forecast_low: ForecastingMatrix | LazyForecastingMatrix
    price_forecast_high: ForecastingMatrix | LazyForecastingMatrix
    id_price: ForecastingMatrix
    da_price: Timeseries | LazyTimeseries
    id_price_forecast: ForecastingMatrix | LazyForecastingMatrix
