from pydantic import ConfigDict

from atlas.config import LoadType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Load(Equipment):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    load_type: LoadType | None = None
    maximum_power_forecast: ForecastingMatrix | None = None
    da_buy_submitted_volume: Timeseries | None = None
    power_forecast_high: Timeseries | None = None
    power_forecast_low: Timeseries | None = None
