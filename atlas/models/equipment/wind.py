from typing import Any

from atlas.models.equipment.equipment import Equipment


class Wind(Equipment):
    installed_capacity: float
    curtailment_power: Any # ForecastMatrix
    maximum_power_forecast: Any # ForecastMatrix
    curtailment_cost: Any # Timeseries
    da_sell_submitted_volume: Any # Timeseries
    maximum_curtailment_ratio: Any # Timeseries