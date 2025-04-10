from pydantic import ConfigDict, Field

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Photovoltaic(Equipment):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    installed_capacity: float | None = Field(
        None,
        gt=0,
        description="Installed capacity (must be positive)",
    )
    maximum_power_forecast: ForecastingMatrix | None = None
    curtailed_power: Timeseries | None = None
    da_sell_submitted_volume: Timeseries | None = None
    maximum_curtailment_ratio: Timeseries | None = None
