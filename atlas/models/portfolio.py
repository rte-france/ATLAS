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


class Portfolio(BusinessModel):
    """
    :param control_block: Installed capacity
    :type control_block: ControlBlock
    :param market_area: Sum of volume of sell offers on the Day Ahead market
    :type market_area: MarketArea
    :param id_cleared_quantity: Sum of the cleared quantities for all equipment in this portfolio in each Intraday Market Clearing
    :type id_cleared_quantity: ForecastingMatrix
    :param imbalance: Portfolio imbalance at the end of each Portfolio optimization. Positive for excess production, and negative in the opposite case.
    :type imbalance: ForecastingMatrix
    :param power: Sum of every power of the Portfolio equipment
    :type power: ForecastingMatrix
    :param afrr_activated: Volume of aFRR activated
    :type afrr_activated: Timeseries
    :param afrr_down_procured: Volume of aFRR reserves contracted downward, summed for all equipment in this portfolio
    :type afrr_down_procured: float
    :param afrr_up_procured: Volume of aFRR reserves contracted upward, summed for all equipment in this portfolio
    :type afrr_up_procured: ForecastingMatrix
    :param da_cleared_quantity: Sum of the cleared quantities for all equipment in this portfolio in the Day Ahead Market Clearing
    :type da_cleared_quantity: ForecastingMatrix
    :param fcr_activated: Volume of FCR activated for this portfolio
    :type fcr_activated: Timeseries
    :param imbalance_settlement_costs: Imbalance costs at the end of the Imbalance Settlement Process
    :type imbalance_settlement_costs: Timeseries
    :param mfrr_activated: Volume of mFRR activated after MARI Clearing
    :type mfrr_activated: Timeseries
    :param mfrr_down_procured: Volume of mFRR reserves contracted downward, summed for all equipment in this portfolio
    :type mfrr_down_procured: ForecastingMatrix
    :param mfrr_up_procured: Volume of mFRR reserves contracted upward, summed for all equipment in this portfolio
    :type mfrr_up_procured: ForecastingMatrix
    :param rr_activated: Volume of RR activated
    :type rr_activated: Timeseries
    :param rr_down_procured: Volume of RR reserves contracted downward, summed for all equipment in this portfolio
    :type rr_down_procured: Timeseries
    :param rr_up_procured: Volume of RR reserves contracted upward, summed for all equipment in this portfolio
    :type rr_up_procured: Timeseries
    :param total_id_cleared_quantity: Cumulative sum of all cleared quantities for equipment in this portfolio across all Intraday Market Clearings
    :type total_id_cleared_quantity: Timeseries
    """

    control_block: ControlBlock | None = None
    market_area: MarketArea | None = None
    id_cleared_quantity: ForecastingMatrix | LazyForecastingMatrix | None = None
    imbalance: ForecastingMatrix | LazyForecastingMatrix | None = None
    power: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_activated: Timeseries | LazyTimeseries | None = None
    afrr_down_procured: Timeseries | LazyTimeseries | None = None
    afrr_up_procured: Timeseries | LazyTimeseries | None = None
    da_cleared_quantity: Timeseries | LazyTimeseries | None = None
    fcr_activated: Timeseries | LazyTimeseries | None = None
    imbalance_settlement_costs: Timeseries | LazyTimeseries | None = None
    mfrr_activated: Timeseries | LazyTimeseries | None = None
    mfrr_down_procured: Timeseries | LazyTimeseries | None = None
    mfrr_up_procured: Timeseries | LazyTimeseries | None = None
    rr_activated: Timeseries | LazyTimeseries | None = None
    rr_down_procured: Timeseries | LazyTimeseries | None = None
    rr_up_procured: Timeseries | LazyTimeseries | None = None
    total_id_cleared_quantity: Timeseries | LazyTimeseries | None = None
