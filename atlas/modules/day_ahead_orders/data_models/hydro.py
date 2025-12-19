from atlas import Hydro, LazyScenarioMatrix, LazyTimeseries, ScenarioMatrix, Timeseries
from atlas.modules.day_ahead_orders.data_models.portfolio import PortfolioDAO


class HydroDAO(Hydro):
    portfolio: PortfolioDAO
    maximum_energy: Timeseries | LazyTimeseries
    minimum_energy: Timeseries | LazyTimeseries
    initial_level: Timeseries | LazyTimeseries
    storage_marginal_value: ScenarioMatrix | LazyScenarioMatrix
    maximum_power: Timeseries | LazyTimeseries
    maximum_curtailment_ratio: Timeseries | LazyTimeseries
