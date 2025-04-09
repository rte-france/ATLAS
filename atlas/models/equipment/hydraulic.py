from typing import List, Any

from atlas.models.equipment.equipment import Equipment


class Hydraulic(Equipment):
    in_flow_frequency: str = None  # possible values : Monthly, Daily
    fragment_prices: List[float]  # positive ?
    fragment_volumes: List[float]  # positive ?
    inflow_frequency: str = None  # possible values : Monthly, Daily
    stored_energy: Any = None  # ForecastMatrix
    da_sell_submitted_volume: Any = None  # Timeseries
    energy_target: Any = None  # Timeseries
    inflows: Any = None  # Timeseries
    initial_level: Any = None  # Timeseries
    maximum_energy: Any = None  # Timeseries
    minimum_energy: Any = None  # Timeseries
    maximum_power: Any = None  # Timeseries
    minimum_power: Any = None  # Timeseries
