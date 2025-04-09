from typing import Any


class Node:
    control_block : str # Class Business model ControlBlock
    market_area: str # Class Business model MarketArea
    balance_forecast: Any # ForecastMatrix
    id_power_injection: Any # ForecastMatrix
    da_power_injection: Any # Timeseries
    reference_balance: Any # Timeseries