from atlas import Portfolio
from atlas.modules.intraday_price_forecast.models.market_area import MarketAreaIDPF


class PortfolioIDPF(Portfolio):
    market_area: MarketAreaIDPF
