from typing import Any, Literal

from atlas.models.equipment.equipment import Equipment


class Storage(Equipment):
    charge_efficiency: float = None  # positive ?
    discharge_efficiency: float = None  # positive ? negative ?
    is_v2g: bool = None
    storage_initial_level: float = None  # positive ?
    storage_type: Literal['Battery', 'PumpedHydraulicStorage', 'ElectricVehicle'] = None
    transition_duration: float = None  # positive ?
    stored_energy: Any = None  # ForecastMatrix
    da_buy_submitted_volume: Any = None  # Timeseries
    da_sell_submitted_volume: Any = None  # Timeseries
    displacement_energy: Any = None  # Timeseries
    maximum_energy: Any = None  # Timeseries
    maximum_power: Any = None  # Timeseries
    minimum_power: Any = None  # Timeseries
    minimum_state_of_charge: Any = None  # Timeseries
