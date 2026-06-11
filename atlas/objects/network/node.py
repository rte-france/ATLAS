"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import field_serializer

from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.core.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.business_model import BusinessModel
from atlas.objects.market.market_area import MarketArea
from atlas.objects.network_operator.control_block import ControlBlock
from atlas.validators import serializer_business_model


class Node(BusinessModel):
    """
    :param control_block: Associated Control block
    :type control_block: ControlBlock
    :param market_area: Associated Market Area
    :type market_area: MarketArea
    :param balance_forecast: Physical balance forecasts on the node for each execution date
    :type balance_forecast: ForecastingMatrix | LazyForecastingMatrix
    :param id_power_injection: Injection (production - consumption) on the node after Intraday Clearing. May be positive, and thus represent demand May be negative, and thus represent withdrawal
    :type id_power_injection: ForecastingMatrix | LazyForecastingMatrix
    :param da_power_injection: Injection (production - consumption) on the node after Day Ahead Clearing.
    May be negative, and thus represent demand
    :type da_power_injection: Timeseries
    :param reference_balance: Nodal reference program for the base case
    :type reference_balance: Timeseries
    """

    control_block: ControlBlock
    market_area: MarketArea
    balance_forecast: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_power_injection: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_power_injection: AbstractTimeseries | None = None
    reference_balance: AbstractTimeseries | None = None

    @field_serializer("control_block", "market_area", mode="plain")
    def serializer_bmo(self, value: BusinessModel | None) -> str | None:
        """Serialize BusinessModel attributes to string."""
        return serializer_business_model(value)
