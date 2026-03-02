from atlas import Portfolio
from atlas.modules.price_forcast.data_models.market_area import MarketAreaIDPF


class PortfolioIDPF(Portfolio):
    market_area: MarketAreaIDPF
