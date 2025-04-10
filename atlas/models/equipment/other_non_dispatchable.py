from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class OtherNonDispatchable(Equipment):
    maximum_power_forecast: ForecastingMatrix | None = None
    da_sell_submitted_volume: Timeseries | None = None
