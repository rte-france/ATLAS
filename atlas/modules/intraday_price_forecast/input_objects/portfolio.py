from atlas.modules.intraday_price_forecast.input_objects.market_area import MarketAreaIDPF
from atlas.objects.market_operator.portfolio import Portfolio


class PortfolioIDPF(Portfolio):
    market_area: MarketAreaIDPF
