from atlas import Solar
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.modules.price_forcast.data_models.portfolio import PortfolioIDPF


class SolarIDPF(Solar):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix
