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
    """:param control_block: Installed capacity
    :type control_block: ControlBlock
    :param market_area: Sum of volume of sell offers on the Day Ahead market
    :type market_area: MarketArea
    :param id_cleared_quantity: Sum of accepted powers of orders for Intraday Clearing
    :type id_cleared_quantity: ForecastingMatrix | LazyForecastingMatrix
    :param imbalance: Portfolio imbalance at the end of each Portfolio optimization. Convention : imbalance is positive
    in the case of excess production, and negative in the opposite case.
    :type imbalance: ForecastingMatrix | LazyForecastingMatrix
    :param power: Sum of every power of the Portfolio equipment
    :type power: ForecastingMatrix | LazyForecastingMatrix
    :param afrr_activated: Volume of AFRR activated
    :type afrr_activated: Timeseries | LazyTimeseries
    :param afrr_down_procured: Volume of AFRR reserves contracted downward
    :type afrr_down_procured: float
    :param afrr_up_procured: Volume of AFRR reserves contracted upward
    :type afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    :param da_cleared_quantity: Sum of accepted power by day-ahead market
    :type da_cleared_quantity: ForecastingMatrix | LazyForecastingMatrix
    :param fcr_activated: Volume of FCR activated
    :type fcr_activated: Timeseries | LazyTimeseries
    :param imbalance_settlement_costs: Imbalance costs at the end of the Imbalance Settlement Process
    :type imbalance_settlement_costs: Timeseries | LazyTimeseries
    :param mfrr_activated: Volume of MFRR activated
    :type mfrr_activated: Timeseries | LazyTimeseries
    :param mfrr_down_procured: Volume of MFRR reserves contracted downward
    :type mfrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    :param mfrr_up_procured: Volume of MFRR reserves contracted upward
    :type mfrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    :param rr_activated: Volume of RR activated
    :type rr_activated: Timeseries | LazyTimeseries
    :param rr_down_procured: Volume of RR reserves contracted downward
    :type rr_down_procured: Timeseries | LazyTimeseries
    :param rr_up_procured: Volume of RR reserves contracted upward
    :type rr_up_procured: Timeseries | LazyTimeseries
    :param total_id_cleared_quantity: Sum of volume of sell offers on the Day Ahead market
    :type total_id_cleared_quantity: Timeseries | LazyTimeseries
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
