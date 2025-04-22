"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.market.market_area import MarketArea


class MarketAreaPtdf(BaseModel):
    """:param market_area: Associated MarketArea
    :type market_area: MarketArea
    :param id_ptdf: PTDF from Flow Based Intraday pre-Clearing
    :type id_ptdf: ForecastingMatrix
    :param da_ptdf: PTDF from Flow Based Day-Ahead pre-Clearing
    :type da_ptdf: Timeseries
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    market_area: MarketArea | None = None
    id_ptdf: ForecastingMatrix | None = None
    da_ptdf: Timeseries | None = None
