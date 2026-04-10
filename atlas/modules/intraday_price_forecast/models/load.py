from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.modules.intraday_price_forecast.models.portfolio import PortfolioIDPF
from atlas.objects.equipment.load import Load


class LoadIDPF(Load):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    # power_forecast_high: AbstractTimeseries
    # power_forecast_low: AbstractTimeseries
