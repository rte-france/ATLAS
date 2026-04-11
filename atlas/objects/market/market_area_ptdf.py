"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import field_serializer

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.business_model import BusinessModel
from atlas.objects.market.market_area import MarketArea
from atlas.validators import serializer_business_model


class MarketAreaPtdf(BusinessModel):
    """
    :param market_area: Associated MarketArea
    :type market_area: MarketArea
    :param id_ptdf: Zonal PTDF (Power Transfer Distribution Factor) for Flow Based Intraday Market(s)
    :type id_ptdf: ForecastingMatrix
    :param da_ptdf: Zonal PTDF (Power Transfer Distribution Factor) for Flow Based Day-Ahead Market
    :type da_ptdf: Timeseries
    """

    market_area: MarketArea
    id_ptdf: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_ptdf: AbstractTimeseries | None = None

    @field_serializer("market_area", mode="plain")
    def serializer_bmo(self, value: BusinessModel | None) -> str | None:
        """Serialize BusinessModel attributes to string."""
        return serializer_business_model(value)
