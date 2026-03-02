from atlas import Solar
from atlas.math.forecasting_matrix import ForecastingMatrix


class SolarIDPF(Solar):
    maximum_power_forecast: ForecastingMatrix
