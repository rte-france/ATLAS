from typing import Any

from atlas.models.equipment.equipment import Equipment


class Load(Equipment):
    load_type: str # possible values : BaseLoad, PowerToGas, OtherNonDispatchableLoad
    maximum_power_forecast: Any # ForecastMatrix
    da_buy_submitted_volume: Any # Timeseries
    power_forecast_high: Any # Timeseries
    power_forecast_low: Any # Timeseries