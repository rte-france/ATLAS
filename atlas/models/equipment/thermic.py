from typing import Any, Literal

from atlas.models.equipment.equipment import Equipment


class Thermic(Equipment):
    installed_capacity: float = None  # positive ?
    minimum_stable_power_duration: float = None  # positive ?
    minimum_time_off: float = None  # positive ?
    minimum_time_on: float = None  # positive ?
    outage_mean_duration: float = None  # positive ?
    outage_probability: float = None  # Between 0 and 1 ?
    scheduled_shutdown_mean_duration: float = None  # positive ?
    scheduled_shutdown_probability: float = None  # Between 0 and 1 ?
    shutdown_duration: float = None  # positive ?
    startup_delay_probability: float = None  # Between 0 and 1 ?
    startup_duration: float = None  # positive ?
    strategy: Literal['Base', 'Intermediate', 'Peak'] = None
    state_sequence: Any = None  # ScenarioMatrix
    da_sell_submitted_volume: Any = None  # Timeseries
    maximum_power: Any = None  # Timeseries
    minimum_power: Any = None  # Timeseries
