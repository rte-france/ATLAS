from pydantic import BaseModel, ConfigDict

from atlas.config import ReservesTypes
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries


class ControlBlock(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    alternative_type: ReservesTypes | None = None
    volume_uncertainty: bool | None = None
    affr_down_required: ForecastingMatrix | None = None
    affr_up_required: ForecastingMatrix | None = None
    balancing_mechanism_needs: ForecastingMatrix | None = None
    mfrr_down_required: ForecastingMatrix | None = None
    mfrr_needs: ForecastingMatrix | None = None
    mfrr_up_required: ForecastingMatrix | None = None
    rr_down_required: ForecastingMatrix | None = None
    rr_needs: ForecastingMatrix | None = None
    rr_up_required: ForecastingMatrix | None = None
    spilled_energy: ForecastingMatrix | None = None
    unsupplied_energy: ForecastingMatrix | None = None
    afrr_activation_costs: Timeseries | None = None
    fcr_activation_costs: Timeseries | None = None
    mfrr_activated: Timeseries | None = None
    mfrr_activation_costs: Timeseries | None = None
    negative_imbalance_price: Timeseries | None = None
    positive_imbalance_price: Timeseries | None = None
    rr_activated: Timeseries | None = None
    rr_activation_costs: Timeseries | None = None
    specific_activated: Timeseries | None = None
    specific_activation_costs: Timeseries | None = None
    weighted_balance_price_down: Timeseries | None = None
    weighted_balance_price_up: Timeseries | None = None
