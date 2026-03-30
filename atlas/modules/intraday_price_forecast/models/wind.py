from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.models.equipment.wind import Wind
from atlas.models.portfolio import Portfolio


class WindIDPF(Wind):
    portfolio: Portfolio
    maximum_power_forecast: ForecastingMatrix
