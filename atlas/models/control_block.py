from typing import Any, Literal

from pydantic import BaseModel


class ControlBlock(BaseModel):
    alternative_type: Literal["FrBM", "mFRR", "aFRR"] = None
    volume_uncertainty: bool = None
    affr_down_required: Any = None  # ForecastMatrix
    affr_up_required: Any = None  # ForecastMatrix
    balancing_mechanism_needs: Any = None  # ForecastMatrix
    mfrr_down_required: Any = None  # ForecastMatrix
    mfrr_needs: Any = None  # ForecastMatrix
    mfrr_up_required: Any = None  # ForecastMatrix
    rr_down_required: Any = None  # ForecastMatrix
    rr_needs: Any = None  # ForecastMatrix
    rr_up_required: Any = None  # ForecastMatrix
    spilled_energy: Any = None  # ForecastMatrix
    unsupplied_energy: Any = None  # ForecastMatrix
    afrr_activation_costs: Any = None  # Timeseries
    fcr_activation_costs: Any = None  # Timeseries
    mfrr_activated: Any = None  # Timeseries
    mfrr_activation_costs: Any = None  # Timeseries
    negative_imbalance_price: Any = None  # Timeseries
    positive_imbalance_price: Any = None  # Timeseries
    rr_activated: Any = None  # Timeseries
    rr_activation_costs: Any = None  # Timeseries
    specific_activated: Any = None  # Timeseries
    specific_activation_costs: Any = None  # Timeseries
    weighted_balance_price_down: Any = None  # Timeseries
    weighted_balance_price_up: Any = None  # Timeseries
