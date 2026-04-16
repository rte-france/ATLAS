from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.wind import Wind


class WindIDPF(Wind):
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
