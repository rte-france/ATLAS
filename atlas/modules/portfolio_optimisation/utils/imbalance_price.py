"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import cast

from pendulum import DateTime

from atlas.enum import MarketType
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.portfolio_optimisation.models.control_block import ControlBlockPO
from atlas.modules.portfolio_optimisation.models.market_area import MarketAreaPO
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters


def estimate_imbalance_prices(
    time: DateTime,
    market_area: MarketAreaPO,
    control_block: ControlBlockPO,
    parameters: PortfolioOptimisationParameters,
) -> tuple[float, float, float, float]:
    """
    Estimate imbalance settlement prices (ISP) at a given time and store them in the provided dictionaries.

    There are four outputs:
      - imbalance_price_up: small upward imbalance
      - large_imbalance_price_up: large upward imbalance
      - imbalance_price_down: small downward imbalance
      - large_imbalance_price_down: large downward imbalance

    Uses either forecast or actual reference price depending on `parameters.use_forecast`,
    and applies either provided imbalance price markers or calculates them using
    French regulation method with penalties and lower bounds.
    """

    if parameters.use_forecast:
        if parameters.market == MarketType.dayahead:
            price = (
                cast(ForecastingMatrix | LazyForecastingMatrix, market_area.price_forecast_medium)
                .get_forecast(parameters.execution_date, time, time)
                .get_value(time)
            )
        elif parameters.market == MarketType.intraday:
            price = (
                cast(ForecastingMatrix | LazyForecastingMatrix, market_area.id_price_forecast)
                .get_forecast(parameters.execution_date, time, time)
                .get_value(time)
            )
        else:
            price = 0.0
    else:
        if parameters.market == MarketType.dayahead:
            price = cast(Timeseries | LazyTimeseries, market_area.da_price).get_value(time)
        elif parameters.market == MarketType.intraday:
            price = (
                cast(ForecastingMatrix | LazyForecastingMatrix, market_area.id_price)
                .get_forecast(parameters.execution_date, time, time)
                .get_value(time)
            )
        elif parameters.market == MarketType.rr_activation:
            price = cast(Timeseries | LazyTimeseries, market_area.rr_activation_price).get_value(time)
        elif parameters.market == MarketType.mfrr_activation:
            price = cast(Timeseries | LazyTimeseries, market_area.mfrr_activation_price).get_value(time)
        else:
            price = 0.0

    # 2. Upward imbalance prices
    if control_block.negative_imbalance_price:
        base = control_block.negative_imbalance_price.get_value(time)
        imbalance_price_up = base * (1 + parameters.small_imbalance_penalty)
        large_imbalance_price_up = base * (1 + parameters.large_imbalance_penalty)
    else:
        if abs(price) < parameters.isp_forecast_lower_bound:
            if price >= 0:
                imbalance_price_up = (1 + parameters.small_imbalance_penalty) * parameters.isp_forecast_lower_bound
                large_imbalance_price_up = (
                    1 + parameters.large_imbalance_penalty
                ) * parameters.isp_forecast_lower_bound
            else:
                imbalance_price_up = (1 - parameters.small_imbalance_penalty) * -parameters.isp_forecast_lower_bound
                large_imbalance_price_up = (
                    1 - parameters.large_imbalance_penalty
                ) * -parameters.isp_forecast_lower_bound
        else:
            if price >= 0:
                imbalance_price_up = (1 + parameters.small_imbalance_penalty) * price
                large_imbalance_price_up = (1 + parameters.large_imbalance_penalty) * price
            else:
                imbalance_price_up = (1 - parameters.small_imbalance_penalty) * price
                large_imbalance_price_up = (1 - parameters.large_imbalance_penalty) * price

    # 3. Downward imbalance prices
    if control_block.positive_imbalance_price:
        base = control_block.positive_imbalance_price.get_value(time)
        imbalance_price_down = base * (1 - parameters.small_imbalance_penalty)
        large_imbalance_price_down = base * (1 - parameters.large_imbalance_penalty)
    else:
        parameters.isp_forecast_lower_bound = parameters.isp_forecast_lower_bound
        if abs(price) < parameters.isp_forecast_lower_bound:
            if price >= 0:
                imbalance_price_down = (1 - parameters.small_imbalance_penalty) * parameters.isp_forecast_lower_bound
                large_imbalance_price_down = (
                    1 - parameters.large_imbalance_penalty
                ) * parameters.isp_forecast_lower_bound
            else:
                imbalance_price_down = (1 + parameters.small_imbalance_penalty) * -parameters.isp_forecast_lower_bound
                large_imbalance_price_down = (
                    1 + parameters.large_imbalance_penalty
                ) * -parameters.isp_forecast_lower_bound
        else:
            if price >= 0:
                imbalance_price_down = (1 - parameters.small_imbalance_penalty) * price
                large_imbalance_price_down = (1 - parameters.large_imbalance_penalty) * price
            else:
                imbalance_price_down = (1 + parameters.small_imbalance_penalty) * price
                large_imbalance_price_down = (1 + parameters.large_imbalance_penalty) * price

    return imbalance_price_down, imbalance_price_up, large_imbalance_price_down, large_imbalance_price_up
