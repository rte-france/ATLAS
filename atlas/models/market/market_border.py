"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel
from atlas.models.control_block import ControlBlock
from atlas.models.market.market_area import MarketArea


class MarketBorder(BusinessModel):
    """
    :param downhill_control_block: Downhill Control Block
    :type downhill_control_block: ControlBlock
    :param uphill_control_block: Uphill Control Block
    :type uphill_control_block: ControlBlock
    :param downhill_market_area: Downhill Market Area
    :type downhill_market_area: MarketArea
    :param uphill_market_area: Uphill Market Area
    :type uphill_market_area: MarketArea
    :param coupling_type: Sum of volume of sell offers on the Day Ahead market
    :type coupling_type: str
    :param loss_factor: Network loss factor
    :type loss_factor: float
    :param time_resolution: Time resolution relative to the border
    :type time_resolution: float
    :param afrr_down_procured: Cross-border contractualization of downward aFRR after the market clearing
    :type afrr_down_procured: ForecastingMatrix
    :param afrr_up_procured: Cross-border contractualization of upward aFRR after the market clearing
    :type afrr_up_procured: ForecastingMatrix
    :param id_flow: Flows from the different Intraday Clearings
    :type id_flow: ForecastingMatrix
    :param id_shadow_price: Shadow prices from the different Intraday Clearings
    :type id_shadow_price: float
    :param mfrr_down_procured: Cross-border contractualization of downward mFRR after the market clearing
    :type mfrr_down_procured: ForecastingMatrix
    :param mfrr_up_procured: Cross-border contractualization of upward mFRR after the market clearing
    :type mfrr_up_procured: ForecastingMatrix
    :param rr_down_procured: Cross-border contractualization of downward RR after the market clearing
    :type rr_down_procured: ForecastingMatrix
    :param rr_up_procured: Cross-border contractualization of upward RR after the market clearing
    :type rr_up_procured: ForecastingMatrix
    :param afrr_activated: Activated aFRR flow across the border
    :type afrr_activated: Timeseries
    :param da_flow: Cross-border flows from the Day Ahead market clearing
    :type da_flow: Timeseries
    :param da_shadow_price: Shadow prices from the Day Ahead market clearing
    :type da_shadow_price: Timeseries
    :param fcr_activated: Activated FCR flow across the border
    :type fcr_activated: Timeseries
    :param maximum_flow: Maximum flow from Uphill Market Area to Downhill Market Area
    :type maximum_flow: Timeseries
    :param mfrr_activated: Activated mFRR flow across the border after MARI market
    :type mfrr_activated: Timeseries
    :param minimum_flow: Minimum flow from Uphill Market Area to Downhill Market Area
    :type minimum_flow: Timeseries
    :param reference_flow: Cross-border reference flow in the base case
    :type reference_flow: Timeseries
    :param rr_activated: Activated RR flow across the border after TERRE market
    :type rr_activated: Timeseries
    :param total_id_flow: Cumulative sum of accepted cross-border quantities from all Intraday market clearings
    :type total_id_flow: Timeseries
    """

    downhill_control_block: ControlBlock | None = None
    uphill_control_block: ControlBlock | None = None
    downhill_market_area: MarketArea | None = None
    uphill_market_area: MarketArea | None = None
    coupling_type: str | None = None
    loss_factor: float | None = None
    time_resolution: float | None = None  # Assuming this can be a float
    afrr_down_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_flow: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_shadow_price: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_down_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_up_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_down_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_up_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_activated: Timeseries | LazyTimeseries | None = None
    da_flow: Timeseries | LazyTimeseries | None = None
    da_shadow_price: Timeseries | LazyTimeseries | None = None
    fcr_activated: Timeseries | LazyTimeseries | None = None
    maximum_flow: Timeseries | LazyTimeseries | None = None
    mfrr_activated: Timeseries | LazyTimeseries | None = None
    minimum_flow: Timeseries | LazyTimeseries | None = None
    reference_flow: Timeseries | LazyTimeseries | None = None
    rr_activated: Timeseries | LazyTimeseries | None = None
    total_id_flow: Timeseries | LazyTimeseries | None = None
