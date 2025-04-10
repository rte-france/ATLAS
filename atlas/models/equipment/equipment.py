from pydantic import BaseModel, ConfigDict, Field

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.scenario_matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries


class Equipment(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    node: str | None = Field(None, description="Class Business model Node")
    portfolio: str | None = Field(None, description="Class Business model Portfolio")
    coe2_emission_factor: float | None = Field(None, description="COE2 emission factor")
    has_daily_energy_constraint: bool | None = None
    maximum_afrr: float | None = None
    maximum_fcr: float | None = None
    maximum_gradient: float | None = None
    setup_delay: float | None = Field(None, gt=0, description="Setup delay (must be positive)")
    unit_count: int | None = Field(None, gt=0, description="Unit count (must be positive)")

    afrr_down_procured: ForecastingMatrix | None = None
    afrr_up_procured: ForecastingMatrix | None = None
    co2_emissions: ForecastingMatrix | None = None
    fcr_down_procured: ForecastingMatrix | None = None
    fcr_up_procured: ForecastingMatrix | None = None
    id_buy_submitted_volume: ForecastingMatrix | None = None
    id_cleared_quantity: ForecastingMatrix | None = None
    id_po_for_orders: ForecastingMatrix | None = None
    id_sell_submitted_volume: ForecastingMatrix | None = None
    mfrr_down_procured: ForecastingMatrix | None = None
    mfrr_up_procured: ForecastingMatrix | None = None
    power: ForecastingMatrix | None = None
    rr_down_procured: ForecastingMatrix | None = None
    rr_up_procured: ForecastingMatrix | None = None
    specific_activated_power: ForecastingMatrix | None = None

    storage_marginal_value: ScenarioMatrix | None = None

    afrr_activated: Timeseries | None = None
    afrr_submitted_volume: Timeseries | None = None
    da_cleared_quantity: Timeseries | None = None
    fcr_activated: Timeseries | None = None
    fcr_submitted_volume: Timeseries | None = None
    maximum_daily_energy: Timeseries | None = None
