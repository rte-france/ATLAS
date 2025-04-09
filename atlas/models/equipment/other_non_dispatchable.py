from typing import Any

from atlas.models.equipment.equipment import Equipment


class OtherNonDispatchable(Equipment):
    maximum_power_forecast: Any # ForecastMatrix
    da_sell_submitted_volume: Any # Timeseries