from typing import List, Any

from atlas.models.equipment.equipment import Equipment


class Hydraulic(Equipment):
    in_flow_frequency: str # possible values : Monthly, Daily
    fragment_prices: List[float] # positive ?
    fragment_volumes: List[float] # positive ?
    inflow_frequency: str # possible values : Monthly, Daily
    stored_energy: Any # ForecastMatrix
    da_sell_submitted_volume: Any # Timeseries
    energy_target: Any # Timeseries
    inflows: Any # Timeseries
    initial_level: Any # Timeseries
    maximum_energy: Any # Timeseries
    minimum_energy: Any # Timeseries
    maximum_power: Any # Timeseries
    minimum_power: Any # Timeseries