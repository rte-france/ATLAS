from atlas import LazyTimeseries, Load, Timeseries
from atlas.modules.day_ahead_orders.orders_formulation.models.portfolio import PortfolioDAO


class LoadDAO(Load):
    portfolio: PortfolioDAO
    variable_cost: Timeseries | LazyTimeseries
