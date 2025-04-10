from pydantic import ConfigDict, Field

from atlas.config import StorageType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Storage(Equipment):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    charge_efficiency: float | None = Field(
        None,
        gt=0,
        description="Charge efficiency (must be positive)",
    )
    discharge_efficiency: float | None = Field(
        None,
        gt=0,
        description="Discharge efficiency (must be positive)",
    )
    is_v2g: bool | None = None
    storage_initial_level: float | None = Field(
        None,
        ge=0,
        description="Initial storage level (positive or zero)",
    )
    storage_type: StorageType | None = None
    transition_duration: float | None = Field(
        None,
        gt=0,
        description="Transition duration (must be positive)",
    )

    stored_energy: ForecastingMatrix | None = None

    da_buy_submitted_volume: Timeseries | None = None
    da_sell_submitted_volume: Timeseries | None = None
    displacement_energy: Timeseries | None = None
    maximum_energy: Timeseries | None = None
    maximum_power: Timeseries | None = None
    minimum_power: Timeseries | None = None
    minimum_state_of_charge: Timeseries | None = None
