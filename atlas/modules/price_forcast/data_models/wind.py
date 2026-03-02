from atlas import Wind
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.modules.price_forcast.data_models.portfolio import PortfolioIDPF


class WindIDPF(Wind):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix
