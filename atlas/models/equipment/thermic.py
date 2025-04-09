from typing import Any

from atlas.models.equipment.equipment import Equipment


class Thermic(Equipment):
    installed_capacity: float # positive ?
    minimum_stable_power_duration: float # positive ?
    minimum_time_off: float # positive ?
    minimum_time_on: float # positive ?
    outage_mean_duration: float # positive ?
    outage_probability: float # Between 0 and 1 ?
    scheduled_shutdown_mean_duration: float # positive ?
    scheduled_shutdown_probability: float # Between 0 and 1 ?
    shutdown_duration: float # positive ?
    startup_delay_probability: float # Between 0 and 1 ?
    startup_duration: float # positive ?
    strategy: str # possibles values : Base, Intermediate, Peak
    state_sequence: Any # ScenarioMatrix
    da_sell_submitted_volume: Any # Timeseries
    maximum_power: Any # Timeseries
    minimum_power: Any # Timeseries