from typing import Any

from atlas.models.equipment.equipment import Equipment


class Wind(Equipment):
    installed_capacity: float = None
    curtailment_power: Any = None  # ForecastMatrix
    maximum_power_forecast: Any = None  # ForecastMatrix
    curtailment_cost: Any = None  # Timeseries
    da_sell_submitted_volume: Any = None  # Timeseries
    maximum_curtailment_ratio: Any = None  # Timeseries
