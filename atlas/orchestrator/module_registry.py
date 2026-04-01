from atlas.modules.day_ahead_orders.module import DayAheadOrdersModule
from atlas.modules.intraday_price_forecast.module import IntradayPriceForecastModule
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule

from enum import Enum

from pydantic import BaseModel, field_validator, model_validator

from atlas.abstract_class.abstract_module import AbstractModule


class ModuleRegistry(Enum):
    """Registry mapping module names to their implementation classes."""

    MarketClearing = MarketClearingModule
    PortfolioOptimisation = PortfolioOptimisationModule
    DayAheadOrders = DayAheadOrdersModule
    IntradayPriceForecast = IntradayPriceForecastModule

    @classmethod
    def get(cls, name: str) -> type[AbstractModule]:
        try:
            return cls[name].value
        except KeyError:
            valid = [m.name for m in cls]
            raise ValueError(f"Unknown module: '{name}'. Valid modules are: {valid}") from None

    @classmethod
    def has_name(cls, name: str) -> bool:
        return name in cls._member_names_
