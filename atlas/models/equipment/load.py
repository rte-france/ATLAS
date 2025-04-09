from typing import Any, Literal

from atlas.models.equipment.equipment import Equipment


class Load(Equipment):
    load_type: Literal['BaseLoad', 'PowerToGas', 'OtherNonDispatchableLoad'] = None
    maximum_power_forecast: Any = None  # ForecastMatrix
    da_buy_submitted_volume: Any = None  # Timeseries
    power_forecast_high: Any = None  # Timeseries
    power_forecast_low: Any = None  # Timeseries
