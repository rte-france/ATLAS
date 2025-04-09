from typing import Any

from atlas.models.equipment.equipment import Equipment


class Photovoltaic(Equipment):
    installed_capacity: float # positive ?
    curtailed_power: Any # ForecastMatrix
    Maximum_power_forecast: Any # ForecastMatrix
    curtailed_power: Any # Timeseries
    da_sell_submitted_volume: Any # Timeseries
    maximum_curtailment_ratio: Any # Timeseries