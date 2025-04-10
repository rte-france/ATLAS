from pydantic import Field

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Hydraulic(Equipment):
    in_flow_frequency: str | None = Field(None, description="Possible values: 'Monthly', 'Daily'")
    inflow_frequency: str | None = Field(None, description="Possible values: 'Monthly', 'Daily'")

    fragment_prices: list[float] = Field(
        ...,
        description="List of positive prices",
    )  # Ajout de validation possible
    fragment_volumes: list[float] = Field(..., description="List of positive volumes")

    stored_energy: ForecastingMatrix | None = None

    da_sell_submitted_volume: Timeseries | None = None
    energy_target: Timeseries | None = None
    inflows: Timeseries | None = None
    initial_level: Timeseries | None = None
    maximum_energy: Timeseries | None = None
    minimum_energy: Timeseries | None = None
    maximum_power: Timeseries | None = None
    minimum_power: Timeseries | None = None
