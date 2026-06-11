from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.core.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.market.market_area import MarketArea


class MarketAreaIDPF(MarketArea):
    price_forecast_low: ForecastingMatrix | LazyForecastingMatrix
    price_forecast_high: ForecastingMatrix | LazyForecastingMatrix
    da_price: AbstractTimeseries
