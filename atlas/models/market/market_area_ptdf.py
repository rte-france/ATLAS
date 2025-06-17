"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel
from atlas.models.market.market_area import MarketArea


class MarketAreaPtdf(BusinessModel):
    """
    :param market_area: Associated MarketArea
    :type market_area: MarketArea
    :param id_ptdf: Zonal PTDF (Power Transfer Distribution Factor) for Flow Based Intraday Market(s)
    :type id_ptdf: ForecastingMatrix
    :param da_ptdf: Zonal PTDF (Power Transfer Distribution Factor) for Flow Based Day-Ahead Market
    :type da_ptdf: Timeseries
    """

    market_area: MarketArea | None = None
    id_ptdf: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_ptdf: Timeseries | LazyTimeseries | None = None
