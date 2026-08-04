"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import field_serializer

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.business_model import BusinessModel
from atlas.objects.network.node import Node
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

    node: Node
    id_ptdf: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_ptdf: AbstractTimeseries | None = None

    _serialize_relations = field_serializer("node", mode="plain")(serializer_business_model)
