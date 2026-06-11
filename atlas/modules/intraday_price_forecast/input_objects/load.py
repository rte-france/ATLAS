from atlas.core.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.equipment.load import Load


class LoadIDPF(Load):
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    # power_forecast_high: AbstractTimeseries
    # power_forecast_low: AbstractTimeseries
