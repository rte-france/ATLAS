from pydantic import model_validator

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.load import Load
from atlas.modules.intraday_price_forecast.models.portfolio import PortfolioIDPF


class LoadIDPF(Load):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix
    # power_forecast_high: AbstractTimeseries
    # power_forecast_low: AbstractTimeseries

    @model_validator(mode="wrap")
    @classmethod
    def convert_portfolio(cls, value, handler, info):
        if isinstance(value, Load):
            data = dict(value)
            if value.portfolio and info.context:
                # Pass context down to PortfolioIDPF validation
                data["portfolio"] = PortfolioIDPF.model_validate(value.portfolio, context=info.context)
            return handler(data)
        return handler(value)
