from typing import Any

from pydantic import BaseModel


class Portfolio(BaseModel):
    control_block: str = None  # Class Business model ControlBlock
    market_area: str = None  # Class Business model MarketArea
    id_cleared_quantity: Any = None  # ForecastMatrix
    imbalance: Any = None  # ForecastMatrix
    power: Any = None  # ForecastMatrix
    afrr_activated: Any = None  # Timeseries
    afrr_down_procured: Any = None  # Timeseries
    afrr_up_procured: Any = None  # Timeseries
    da_cleared_quantity: Any = None  # Timeseries
    fcr_activated: Any = None  # Timeseries
    imbalance_settlement_costs: Any = None  # Timeseries
    mfrr_activated: Any = None  # Timeseries
    mfrr_down_procured: Any = None  # Timeseries
    mfrr_up_procured: Any = None  # Timeseries
    rr_activated: Any = None  # Timeseries
    rr_down_procured: Any = None  # Timeseries
    rr_up_procured: Any = None  # Timeseries
    total_id_cleared_quantity: Any = None  # Timeseries
