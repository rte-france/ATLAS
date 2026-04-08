from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.modules.intraday_price_forecast.models.portfolio import PortfolioIDPF
from atlas.objects.equipment.solar import Solar


class SolarIDPF(Solar):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
