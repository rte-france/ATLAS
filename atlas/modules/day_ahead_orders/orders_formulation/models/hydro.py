from atlas import Hydro, LazyScenarioMatrix, LazyTimeseries, ScenarioMatrix, Timeseries
from atlas.modules.day_ahead_orders.orders_formulation.models.portfolio import PortfolioDAO


class HydroDAO(Hydro):
    portfolio: PortfolioDAO
    maximum_energy: Timeseries | LazyTimeseries
    minimum_energy: Timeseries | LazyTimeseries
    initial_level: Timeseries | LazyTimeseries
    storage_marginal_value: ScenarioMatrix | LazyScenarioMatrix
    maximum_power: Timeseries | LazyTimeseries
