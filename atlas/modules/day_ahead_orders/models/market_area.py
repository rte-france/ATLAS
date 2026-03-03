"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.market.market_area import MarketArea


class MarketAreaDAO(MarketArea):
    price_forecast_low: ForecastingMatrix | LazyForecastingMatrix
    price_forecast_medium: ForecastingMatrix | LazyForecastingMatrix
    price_forecast_high: ForecastingMatrix | LazyForecastingMatrix
