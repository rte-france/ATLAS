from typing import Any

from pydantic import BaseModel


class MarketBorder(BaseModel):
    downhill_control_block: str = None  # Class Business model ControlBlock
    uphill_control_block: str = None  # Class Business model ControlBlock
    downhill_market_area: str = None  # Class Business model MarketArea
    uphill_market_area: str = None  # Class Business model MarketArea
    coupling_type: str = None
    loss_factor: float = None
    time_resolution: float = None  # positive ?
    afrr_down_procured: Any = None  # ForecastMatrix
    afrr_up_procured: Any = None  # ForecastMatrix
    id_flow: Any = None  # ForecastMatrix
    id_shadow_price: Any = None  # ForecastMatrix
    mfrr_down_procured: Any = None  # ForecastMatrix
    mfrr_up_procured: Any = None  # ForecastMatrix
    rr_down_procured: Any = None  # ForecastMatrix
    rr_up_procured: Any = None  # ForecastMatrix
    afrr_activated: Any = None  # Timeseries
    da_flow: Any = None  # Timeseries
    da_shadow_price: Any = None  # Timeseries
    fcr_activated: Any = None  # Timeseries
    maximum_flow: Any = None  # Timeseries
    mfrr_activated: Any = None  # Timeseries
    minimum_flow: Any = None  # Timeseries
    reference_flow: Any = None  # Timeseries
    rr_activated: Any = None  # Timeseries
    total_id_flow: Any = None  # Timeseries
