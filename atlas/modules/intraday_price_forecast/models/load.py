from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.load import Load
from atlas.modules.intraday_price_forecast.models.portfolio import PortfolioIDPF


class LoadIDPF(Load):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
