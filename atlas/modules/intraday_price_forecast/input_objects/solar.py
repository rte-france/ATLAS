from atlas.core.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.solar import Solar


class SolarIDPF(Solar):
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
