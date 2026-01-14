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


def _get_reference_price(
    time: DateTime,
    market_area: MarketAreaPO,
    parameters: PortfolioOptimisationParameters,
) -> float:
    """
    Get the reference price for imbalance calculation.

    Returns either forecast or actual price depending on parameters.use_forecast
    and parameters.market type.

    :param time: Current time period
    :type time: DateTime
    :param market_area: Market area object
    :type market_area: MarketAreaPO
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Reference price
    :rtype: float
    """
    if parameters.use_forecast:
        return _get_forecast_price(time, market_area, parameters)
    return _get_actual_price(time, market_area, parameters)


def _get_forecast_price(
    time: DateTime,
    market_area: MarketAreaPO,
    parameters: PortfolioOptimisationParameters,
) -> float:
    """
    Get forecast price based on market type.

    :param time: Current time period
    :type time: DateTime
    :param market_area: Market area object
    :type market_area: MarketAreaPO
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Forecast price
    :rtype: float
    """
    if parameters.market == MarketType.dayahead:
        return (
            cast(ForecastingMatrix | LazyForecastingMatrix, market_area.price_forecast_medium)
            .get_forecast(parameters.execution_date, time, time)
            .get_value(time)
        )
    elif parameters.market == MarketType.intraday:
        return (
            cast(ForecastingMatrix | LazyForecastingMatrix, market_area.id_price_forecast)
            .get_forecast(parameters.execution_date, time, time)
            .get_value(time)
        )
    return 0.0


def _get_actual_price(
    time: DateTime,
    market_area: MarketAreaPO,
    parameters: PortfolioOptimisationParameters,
) -> float:
    """
    Get actual price based on market type.

    :param time: Current time period
    :type time: DateTime
    :param market_area: Market area object
    :type market_area: MarketAreaPO
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Actual price
    :rtype: float
    """
    if parameters.market == MarketType.dayahead:
        return cast(Timeseries | LazyTimeseries, market_area.da_price).get_value(time)
    elif parameters.market == MarketType.intraday:
        return (
            cast(ForecastingMatrix | LazyForecastingMatrix, market_area.id_price)
            .get_forecast(parameters.execution_date, time, time)
            .get_value(time)
        )
    elif parameters.market == MarketType.rr_activation:
        return cast(Timeseries | LazyTimeseries, market_area.rr_activation_price).get_value(time)
    elif parameters.market == MarketType.mfrr_activation:
        return cast(Timeseries | LazyTimeseries, market_area.mfrr_activation_price).get_value(time)
    return 0.0


def _calculate_imbalance_with_penalty(
    base_price: float,
    lower_bound: float,
    small_penalty: float,
    large_penalty: float,
    apply_upward: bool,
) -> tuple[float, float]:
    """
    Calculate imbalance prices with penalties applied.

    :param base_price: Reference price to apply penalties to
    :type base_price: float
    :param lower_bound: Minimum absolute price threshold
    :type lower_bound: float
    :param small_penalty: Penalty factor for small imbalances
    :type small_penalty: float
    :param large_penalty: Penalty factor for large imbalances
    :type large_penalty: float
    :param apply_upward: If True, penalties increase prices (upward imbalance).
                        If False, penalties decrease prices (downward imbalance).
    :type apply_upward: bool
    :return: Tuple of (small_imbalance_price, large_imbalance_price)
    :rtype: tuple[float, float]
    """
    # Determine effective price considering lower bound
    if abs(base_price) < lower_bound:
        effective_price = lower_bound if base_price >= 0 else -lower_bound
    else:
        effective_price = base_price

    # Apply penalties based on direction
    if apply_upward:
        # Upward imbalance: penalties increase prices when positive, decrease when negative
        if effective_price >= 0:
            small_price = effective_price * (1 + small_penalty)
            large_price = effective_price * (1 + large_penalty)
        else:
            small_price = effective_price * (1 - small_penalty)
            large_price = effective_price * (1 - large_penalty)
    else:
        # Downward imbalance: penalties decrease prices when positive, increase when negative
        if effective_price >= 0:
            small_price = effective_price * (1 - small_penalty)
            large_price = effective_price * (1 - large_penalty)
        else:
            small_price = effective_price * (1 + small_penalty)
            large_price = effective_price * (1 + large_penalty)

    return small_price, large_price


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

    :param time: Current time period
    :type time: DateTime
    :param market_area: Market area object
    :type market_area: MarketAreaPO
    :param control_block: Control block object
    :type control_block: ControlBlockPO
    :param parameters: Optimization parameters
    :type parameters: PortfolioOptimisationParameters
    :return: Tuple of (imbalance_price_down, imbalance_price_up, large_imbalance_price_down, large_imbalance_price_up)
    :rtype: tuple[float, float, float, float]
    """
    # Get reference price
    price = _get_reference_price(time, market_area, parameters)

    # Calculate upward imbalance prices
    if control_block.negative_imbalance_price:
        base = control_block.negative_imbalance_price.get_value(time)
        imbalance_price_up = base * (1 + parameters.small_imbalance_penalty)
        large_imbalance_price_up = base * (1 + parameters.large_imbalance_penalty)
    else:
        imbalance_price_up, large_imbalance_price_up = _calculate_imbalance_with_penalty(
            price,
            parameters.isp_forecast_lower_bound,
            parameters.small_imbalance_penalty,
            parameters.large_imbalance_penalty,
            apply_upward=True,
        )

    # Calculate downward imbalance prices
    if control_block.positive_imbalance_price:
        base = control_block.positive_imbalance_price.get_value(time)
        imbalance_price_down = base * (1 - parameters.small_imbalance_penalty)
        large_imbalance_price_down = base * (1 - parameters.large_imbalance_penalty)
    else:
        imbalance_price_down, large_imbalance_price_down = _calculate_imbalance_with_penalty(
            price,
            parameters.isp_forecast_lower_bound,
            parameters.small_imbalance_penalty,
            parameters.large_imbalance_penalty,
            apply_upward=False,
        )

    return imbalance_price_down, imbalance_price_up, large_imbalance_price_down, large_imbalance_price_up
