from typing import Any


class Equipment:
    node: str # Class Business model Node
    portfolio: str # Class Business model Portfolio
    coe2_emission_factor: float
    has_daily_energy_constraint: bool
    maximum_afrr : float
    maximum_fcr : float
    maximum_gradient: float
    setup_delay: float # positive ?
    unit_count: int # positive ?
    afrr_down_procured: Any # ForecastMatrix
    afrr_up_procured: Any # ForecastMatrix
    co2_emissions: Any # ForecastMatrix
    fcr_down_procured: Any # ForecastMatrix
    fcr_up_procured: Any # ForecastMatrix
    id_buy_submitted_volume: Any # ForecastMatrix
    id_cleared_quantity: Any # ForecastMatrix
    id_po_for_orders: Any # ForecastMatrix
    id_sell_submitted_volume: Any # ForecastMatrix
    mfrr_down_procured: Any # ForecastMatrix
    mfrr_up_procured: Any # ForecastMatrix
    power: Any # ForecastMatrix
    rr_down_procured: Any # ForecastMatrix
    rr_up_procured: Any # ForecastMatrix
    specific_activated_power: Any # ForecastMatrix
    storage_marginal_value: Any # ScenarioMatrix
    afrr_activated: Any # Timeseries
    afrr_submitted_volume: Any # Timeseries
    da_cleared_quantity: Any # Timeseries
    fcr_activated: Any # Timeseries
    fcr_submitted_volume: Any # Timeseries
    maximum_daily_energy: Any # Timeseries
    mfrr_activated: Any # Timeseries
    mfrr_submitted_volume: Any # Timeseries
    minimum_daily_energy: Any # Timeseries
    rr_activated: Any # Timeseries
    rr_submitted_volume: Any # Timeseries
    startup_cost: Any # Timeseries
    total_id_buy_submitted_volume: Any # Timeseries
    total_id_cleared_quantity: Any # Timeseries
    total_id_sell_submitted_volume: Any # Timeseries
    variable_cost: Any # Timeseries