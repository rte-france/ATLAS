from typing import Any


class MarketBorder:
    downhill_control_block: str # Class Business model ControlBlock
    uphill_control_block: str # Class Business model ControlBlock
    downhill_market_area: str # Class Business model MarketArea
    uphill_market_area: str # Class Business model MarketArea
    coupling_type: str
    loss_factor: float
    time_resolution: float # positive ?
    afrr_down_procured: Any # ForecastMatrix
    afrr_up_procured: Any # ForecastMatrix
    id_flow: Any # ForecastMatrix
    id_shadow_price: Any # ForecastMatrix
    mfrr_down_procured: Any # ForecastMatrix
    mfrr_up_procured: Any # ForecastMatrix
    rr_down_procured: Any # ForecastMatrix
    rr_up_procured: Any # ForecastMatrix
    afrr_activated: Any # Timeseries
    da_flow: Any # Timeseries
    da_shadow_price: Any # Timeseries
    fcr_activated: Any # Timeseries
    maximum_flow: Any # Timeseries
    mfrr_activated: Any # Timeseries
    minimum_flow: Any # Timeseries
    reference_flow: Any # Timeseries
    rr_activated: Any # Timeseries
    total_id_flow: Any # Timeseries