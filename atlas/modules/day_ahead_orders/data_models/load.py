from atlas import LazyTimeseries, Load, Timeseries
from atlas.modules.day_ahead_orders.data_models.portfolio import PortfolioDAO


class LoadDAO(Load):
    portfolio: PortfolioDAO
    variable_cost: Timeseries | LazyTimeseries
