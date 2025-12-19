from atlas import LazyTimeseries, Timeseries, Wind
from atlas.modules.day_ahead_orders.data_models.portfolio import PortfolioDAO


class WindDAO(Wind):
    portfolio: PortfolioDAO
    maximum_curtailment_ratio: Timeseries | LazyTimeseries
