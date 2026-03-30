from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.load import Load
from atlas.models.portfolio import Portfolio


class LoadIDPF(Load):
    portfolio: Portfolio
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
