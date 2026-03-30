from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.wind import Wind
from atlas.modules.intraday_price_forecast.models.portfolio import PortfolioIDPF


class WindIDPF(Wind):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
