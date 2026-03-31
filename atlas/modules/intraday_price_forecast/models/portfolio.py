from pydantic import model_validator

from atlas import Portfolio
from atlas.modules.intraday_price_forecast.models.market_area import MarketAreaIDPF


class PortfolioIDPF(Portfolio):
    market_area: MarketAreaIDPF

    @model_validator(mode="wrap")
    @classmethod
    def convert_market_area(cls, value, handler, info):
        if isinstance(value, Portfolio):
            data = dict(value)
            if value.market_area:
                # Get market_area_map from context
                market_area_map = info.context.get("market_area_map", {}) if info.context else {}
                if market_area_map and value.market_area.name in market_area_map:
                    data["market_area"] = market_area_map[value.market_area.name]
            return handler(data)
        return handler(value)
