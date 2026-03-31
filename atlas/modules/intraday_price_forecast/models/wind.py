from pydantic import model_validator

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.equipment.wind import Wind
from atlas.modules.intraday_price_forecast.models.portfolio import PortfolioIDPF


class WindIDPF(Wind):
    portfolio: PortfolioIDPF
    maximum_power_forecast: ForecastingMatrix | LazyForecastingMatrix

    @model_validator(mode="wrap")
    @classmethod
    def convert_portfolio(
        cls,
        value,
        handler,
    ):
        if isinstance(value, Wind):
            data = dict(value)
            if value.portfolio and info.context:
                # Pass context down to PortfolioIDPF validation
                data["portfolio"] = PortfolioIDPF.model_validate(value.portfolio, context=info.context)
            return handler(data)
        return handler(value)
