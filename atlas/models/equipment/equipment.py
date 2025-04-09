from typing import Any

from pydantic import BaseModel


class Equipment(BaseModel):
    node: str = None  # Class Business model Node
    portfolio: str = None  # Class Business model Portfolio
    coe2_emission_factor: float = None
    has_daily_energy_constraint: bool = None
    maximum_afrr: float = None
    maximum_fcr: float = None
    maximum_gradient: float = None
    setup_delay: float = None  # positive ?
    unit_count: int = None  # positive ?
    afrr_down_procured: Any = None  # ForecastMatrix
    afrr_up_procured: Any = None  # ForecastMatrix
    co2_emissions: Any = None  # ForecastMatrix
    fcr_down_procured: Any = None  # ForecastMatrix
    fcr_up_procured: Any = None  # ForecastMatrix
    id_buy_submitted_volume: Any = None  # ForecastMatrix
    id_cleared_quantity: Any = None  # ForecastMatrix
    id_po_for_orders: Any = None  # ForecastMatrix
    id_sell_submitted_volume: Any = None  # ForecastMatrix
    mfrr_down_procured: Any = None  # ForecastMatrix
    mfrr_up_procured: Any = None  # ForecastMatrix
    power: Any = None  # ForecastMatrix
    rr_down_procured: Any = None  # ForecastMatrix
    rr_up_procured: Any = None  # ForecastMatrix
    specific_activated_power: Any = None  # ForecastMatrix
    storage_marginal_value: Any = None  # ScenarioMatrix
    afrr_activated: Any = None  # Timeseries
    afrr_submitted_volume: Any = None  # Timeseries
    da_cleared_quantity: Any = None  # Timeseries
    fcr_activated: Any = None  # Timeseries
    fcr_submitted_volume: Any = None  # Timeseries
    maximum_daily_energy: Any = None  # Timeseries
    mfrr_activated: Any = None  # Timeseries
    mfrr_submitted_volume: Any = None  # Timeseries
    minimum_daily_energy: Any = None  # Timeseries
    rr_activated: Any = None  # Timeseries
    rr_submitted_volume: Any = None  # Timeseries
    startup_cost: Any = None  # Timeseries
    total_id_buy_submitted_volume: Any = None  # Timeseries
    total_id_cleared_quantity: Any = None  # Timeseries
    total_id_sell_submitted_volume: Any = None  # Timeseries
    variable_cost: Any = None  # Timeseries
