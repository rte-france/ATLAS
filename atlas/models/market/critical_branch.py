"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.market.market_area_ptdf import MarketAreaPtdf
from atlas.models.market.node_ptdf import NodePtdf
from atlas.models.node import Node


class CriticalBranch(BaseModel):
    """:param downhill_node: Downhill node
    :type downhill_node: Node
    :param uphill_node: Uphill node
    :type uphill_node: Node
    :param market_area_ptdf: Associated Market Area PTDF
    :type market_area_ptdf: MarketAreaPtdf
    :param node_ptdf: Associated Node PTDF
    :type node_ptdf: NodePtdf
    :param id_flow: Power transiting through this critical branch for each hour of the Intraday, for each ExecutionDate
    :type id_flow: ForecastingMatrix
    :param id_shadow_price: Shadow prices of the various Intraday clearing, for each ExecutionDate
    :type id_shadow_price: ForecastingMatrix
    :param da_flow: Power transiting through this critical branch, after Day Ahead clearing
    :type da_flow: Timeseries
    :param da_shadow_price: Shadow prices for Day Ahead clearing orders
    :type da_shadow_price: Timeseries
    :param flow_reliability_margin: Safety margin to avoid forecast errors or uncertainties, in the Flow Based model
    :type flow_reliability_margin: Timeseries
    :param maximum_flow: Maximum power allowed on this branch
    :type maximum_flow: Timeseries
    :param reference_flow: Reference flow, i.e. forecast prior to an electricity market
    :type reference_flow: Timeseries
    :param total_id_flow: For each Intraday time step, cumulative sum of flows transiting the line after the various
    Intraday clearing operations
    :type total_id_flow: Timeseries
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    downhill_node: Node | None = None
    uphill_node: Node | None = None
    market_area_ptdf: MarketAreaPtdf | None = None
    node_ptdf: NodePtdf | None = None
    id_flow: ForecastingMatrix | None = None
    id_shadow_price: ForecastingMatrix | None = None
    da_flow: Timeseries | None = None
    da_shadow_price: Timeseries | None = None
    flow_reliability_margin: Timeseries | None = None
    maximum_flow: Timeseries | None = None
    reference_flow: Timeseries | None = None
    total_id_flow: Timeseries | None = None
