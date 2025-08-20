"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel
from atlas.models.market.market_area_ptdf import MarketAreaPtdf
from atlas.models.market.node_ptdf import NodePtdf
from atlas.models.node import Node


class CriticalBranch(BusinessModel):
    """
    :param downhill_node: Downhill node
    :type downhill_node: Node
    :param uphill_node: Uphill node
    :type uphill_node: Node
    :param market_area_ptdf: Associated Market Area PTDF
    :type market_area_ptdf: MarketAreaPtdf
    :param node_ptdf: Associated Node PTDF
    :type node_ptdf: NodePtdf
    :param id_flow: Power transiting through this critical branch for each Intraday market
    :type id_flow: ForecastingMatrix
    :param id_shadow_price: Critical branch shadow prices of the various Intraday clearings, for each execution_date
    :type id_shadow_price: ForecastingMatrix
    :param da_flow: Power transiting through this critical branch after the Day Ahead market clearing
    :type da_flow: Timeseries
    :param da_shadow_price: Critical branch shadow prices for the Day Ahead market clearing
    :type da_shadow_price: Timeseries
    :param flow_reliability_margin: Safety margin to avoid forecast errors or uncertainties, in the Flow Based model
    :type flow_reliability_margin: Timeseries | LazyTimeseries
    :param maximum_flow: Maximum power allowed on this branch
    :type maximum_flow: Timeseries
    :param reference_flow: Reference flow in the base case, i.e. forecasted flow prior to an electricity market
    :type reference_flow: Timeseries
    :param total_id_flow: Cumulative sum of flows transiting the line for all Intraday clearing operations
    :type total_id_flow: Timeseries

    """

    downhill_node: Node | None = None
    uphill_node: Node | None = None
    market_area_ptdf: list[MarketAreaPtdf] | None = None
    node_ptdf: list[NodePtdf] | None = None
    id_flow: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_shadow_price: ForecastingMatrix | LazyForecastingMatrix | None = None
    da_flow: Timeseries | LazyTimeseries | None = None
    da_shadow_price: Timeseries | LazyTimeseries | None = None
    flow_reliability_margin: Timeseries | LazyTimeseries | None = None
    maximum_flow: Timeseries | LazyTimeseries | None = None
    reference_flow: Timeseries | LazyTimeseries | None = None
    total_id_flow: Timeseries | LazyTimeseries | None = None
