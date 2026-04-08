from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.modules.intraday_price_forecast.models.portfolio import PortfolioIDPF
from atlas.objects.equipment.wind import Wind


class WindIDPF(Wind):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
