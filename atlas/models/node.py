"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.market.market_area import MarketArea


class Node(BaseModel):
    """:param control_block: Associated Control block
    :type control_block: ControlBlock
    :param market_area: Associated Market Area
    :type market_area: MarketArea
    :param balance_forecast: Physical balance forecasts on the node for each execution date
    :type balance_forecast: ForecastingMatrix
    :param id_power_injection: Injection (production - consumption) on the node after Intraday Clearing.
    May be negative, and thus represent withdrawal
    :type id_power_injection: ForecastingMatrix
    :param da_power_injection: Injection (production - consumption) on the node after Day Ahead Clearing.
    May be negative, and thus represent withdrawal
    :type da_power_injection: Timeseries
    :param reference_balance: Balance define by GRT
    :type reference_balance: Timeseries
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    control_block: ControlBlock | None = None
    market_area: MarketArea | None = None
    balance_forecast: ForecastingMatrix | None = None
    id_power_injection: ForecastingMatrix | None = None
    da_power_injection: Timeseries | None = None
    reference_balance: Timeseries | None = None
