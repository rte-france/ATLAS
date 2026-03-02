from atlas import Load
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.price_forecast.data_models.portfolio import PortfolioIDPF


class LoadIDPF(Load):
    portfolio: PortfolioIDPF
    variable_cost: Timeseries | LazyTimeseries
    maximum_power_forecast: ForecastingMatrix
