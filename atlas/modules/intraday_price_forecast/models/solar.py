from pydantic import model_validator

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.solar import Solar
from atlas.modules.intraday_price_forecast.models.portfolio import PortfolioIDPF


class SolarIDPF(Solar):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix

    @model_validator(mode="wrap")
    @classmethod
    def convert_portfolio(cls, value, handler):
        if isinstance(value, Solar):
            data = dict(value)
            if value.portfolio:
                # Pass context down to PortfolioIDPF validation
                data["portfolio"] = PortfolioIDPF.model_validate(value.portfolio)
            return handler(data)
        return handler(value)
