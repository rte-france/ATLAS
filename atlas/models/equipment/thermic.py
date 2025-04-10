from pydantic import Field

from atlas.config import ThermicStrategy
from atlas.math.scenario_matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.equipment.equipment import Equipment


class Thermic(Equipment):
    installed_capacity: float | None = Field(
        None,
        gt=0,
        description="Installed capacity (must be positive)",
    )
    minimum_stable_power_duration: float | None = Field(None, gt=0)
    minimum_time_off: float | None = Field(None, gt=0)
    minimum_time_on: float | None = Field(None, gt=0)
    outage_mean_duration: float | None = Field(None, gt=0)
    outage_probability: float | None = Field(None, ge=0, le=1)
    scheduled_shutdown_mean_duration: float | None = Field(None, gt=0)
    scheduled_shutdown_probability: float | None = Field(None, ge=0, le=1)
    shutdown_duration: float | None = Field(None, gt=0)
    startup_delay_probability: float | None = Field(None, ge=0, le=1)
    startup_duration: float | None = Field(None, gt=0)

    strategy: ThermicStrategy | None = None

    state_sequence: ScenarioMatrix | None = None
    da_sell_submitted_volume: Timeseries | None = None
    maximum_power: Timeseries | None = None
    minimum_power: Timeseries | None = None
