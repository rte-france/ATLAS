from atlas import Load
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries


class LoadIDPF(Load):
    variable_cost: Timeseries | LazyTimeseries
    maximum_power_forecast: ForecastingMatrix
