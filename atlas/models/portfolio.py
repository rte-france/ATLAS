from typing import Any

from atlas.models.equipment.equipment import Equipment


class Portfolio(Equipment):
    control_block: str # Class Business model ControlBlock
    market_area: str # Class Business model MarketArea
    id_cleared_quantity: Any # ForecastMatrix
    imbalance: Any # ForecastMatrix
    power: Any # ForecastMatrix
    afrr_activated: Any # Timeseries
    afrr_down_procured: Any # Timeseries
    afrr_up_procured: Any # Timeseries
    da_cleared_quantity: Any # Timeseries
    fcr_activated: Any # Timeseries
    imbalance_settlement_costs: Any # Timeseries
    mfrr_activated: Any # Timeseries
    mfrr_down_procured: Any # Timeseries
    mfrr_up_procured: Any # Timeseries
    rr_activated: Any # Timeseries
    rr_down_procured: Any # Timeseries
    rr_up_procured: Any # Timeseries
    total_id_cleared_quantity: Any # Timeseries