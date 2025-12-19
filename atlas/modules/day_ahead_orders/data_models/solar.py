from atlas import LazyTimeseries, Solar, Timeseries
from atlas.modules.day_ahead_orders.data_models.portfolio import PortfolioDAO


class SolarDAO(Solar):
    portfolio: PortfolioDAO
    maximum_curtailment_ratio: Timeseries | LazyTimeseries
