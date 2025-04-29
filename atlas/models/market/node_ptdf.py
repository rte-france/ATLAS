"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel
from atlas.models.node import Node


class NodePtdf(BusinessModel):
    """:param node: Associated Node
    :type node: Node
    :param id_ptdf: PTDF from Flow Based Intraday pre-Clearing
    :type id_ptdf: ForecastingMatrix
    :param da_ptdf: PTDF from Flow Based Day-Ahead pre-Clearing
    :type da_ptdf: ForecastingMatrix
    """

    node: Node | None = None
    id_ptdf: ForecastingMatrix | None = None
    da_ptdf: Timeseries | None = None
