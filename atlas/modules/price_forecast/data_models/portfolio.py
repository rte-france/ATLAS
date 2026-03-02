from atlas import Portfolio
from atlas.modules.price_forecast.data_models.market_area import MarketAreaIDPF


class PortfolioIDPF(Portfolio):
    market_area: MarketAreaIDPF
