from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.models.equipment.solar import Solar
from atlas.models.portfolio import Portfolio


class SolarIDPF(Solar):
    portfolio: Portfolio
    maximum_power_forecast: ForecastingMatrix
