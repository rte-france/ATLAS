"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.market.market_area import MarketArea


class MarketAreaPO(MarketArea):
    price_forecast_medium: ForecastingMatrix | LazyForecastingMatrix
    da_price: Timeseries | LazyTimeseries
    # id_price: ForecastingMatrix | LazyForecastingMatrix
    # rr_activation_price: Timeseries | LazyTimeseries
    # mfrr_activation_price: Timeseries | LazyTimeseries
    # id_price_forecast: ForecastingMatrix | LazyForecastingMatrix
