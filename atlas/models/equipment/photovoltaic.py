from typing import Any

from atlas.models.equipment.equipment import Equipment


class Photovoltaic(Equipment):
    installed_capacity: float = None  # positive ?
    curtailed_power: Any = None  # ForecastMatrix
    Maximum_power_forecast: Any = None  # ForecastMatrix
    curtailed_power: Any = None  # Timeseries
    da_sell_submitted_volume: Any = None  # Timeseries
    maximum_curtailment_ratio: Any = None  # Timeseries
