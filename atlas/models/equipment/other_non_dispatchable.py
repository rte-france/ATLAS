from pydantic import ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class OtherNonDispatchable(Equipment):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    maximum_power_forecast: ForecastingMatrix | None = None
    da_sell_submitted_volume: Timeseries | None = None
