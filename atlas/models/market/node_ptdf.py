"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import field_serializer

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.models.business_model import BusinessModel
from atlas.models.network.node import Node
from atlas.validators import serializer_business_model


class NodePtdf(BusinessModel):
    """
    :param node: Associated Node
    :type node: Node
    :param id_ptdf: Nodal PTDF (Power Transfer Distribution Factor) for Flow Based Intraday Market(s)
    :type id_ptdf: ForecastingMatrix
    :param da_ptdf: Nodal PTDF (Power Transfer Distribution Factor) for Flow Based Day-Ahead Market
    :type da_ptdf: ForecastingMatrix
    """

    node: Node | None = None
    id_ptdf: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_ptdf: AbstractTimeseries | None = None

    @field_serializer("node", mode="plain")
    def serializer_bmo(self, value: BusinessModel | None) -> str | None:
        """Serialize BusinessModel attributes to string."""
        return serializer_business_model(value)
