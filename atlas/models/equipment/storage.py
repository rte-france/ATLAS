from typing import Any

from atlas.models.equipment.equipment import Equipment


class Storage(Equipment):
    charge_efficiency: float # positive ?
    discharge_efficiency: float # positive ? negative ?
    is_v2g: bool
    storage_initial_level: float # positive ?
    storage_type: str # possibles values : Battery, PumpedHydraulicStorage, ElectricVehicle
    transition_duration: float # positive ?
    stored_energy: Any # ForecastMatrix
    da_buy_submitted_volume: Any # Timeseries
    da_sell_submitted_volume: Any # Timeseries
    displacement_energy: Any # Timeseries
    maximum_energy: Any # Timeseries
    maximum_power: Any # Timeseries
    minimum_power: Any # Timeseries
    minimum_state_of_charge: Any # Timeseries