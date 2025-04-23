"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix
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
    :type id_cleared_quantity: ForecastingMatrix
    :param imbalance: Portfolio imbalance at the end of each Portfolio optimization. Convention : imbalance is positive
    in the case of excess production, and negative in the opposite case.
    :type imbalance: ForecastingMatrix
    :param power: Sum of every power of the Portfolio equipment
    :type power: ForecastingMatrix
    :param afrr_activated: Volume of AFRR activated
    :type afrr_activated: Timeseries
    :param afrr_down_procured: Volume of AFRR reserves contracted downward
    :type afrr_down_procured: float
    :param afrr_up_procured: Volume of AFRR reserves contracted upward
    :type afrr_up_procured: ForecastingMatrix
    :param da_cleared_quantity: Sum of accepted power by day-ahead market
    :type da_cleared_quantity: ForecastingMatrix
    :param fcr_activated: Volume of FCR activated
    :type fcr_activated: Timeseries
    :param imbalance_settlement_costs: Imbalance costs at the end of the Imbalance Settlement Process
    :type imbalance_settlement_costs: Timeseries
    :param mfrr_activated: Volume of MFRR activated
    :type mfrr_activated: Timeseries
    :param mfrr_down_procured: Volume of MFRR reserves contracted downward
    :type mfrr_down_procured: ForecastingMatrix
    :param mfrr_up_procured: Volume of MFRR reserves contracted upward
    :type mfrr_up_procured: ForecastingMatrix
    :param rr_activated: Volume of RR activated
    :type rr_activated: Timeseries
    :param rr_down_procured: Volume of RR reserves contracted downward
    :type rr_down_procured: Timeseries
    :param rr_up_procured: Volume of RR reserves contracted upward
    :type rr_up_procured: Timeseries
    :param total_id_cleared_quantity: Sum of volume of sell offers on the Day Ahead market
    :type total_id_cleared_quantity: Timeseries
    """

    control_block: ControlBlock | None = None
    market_area: MarketArea | None = None
    id_cleared_quantity: ForecastingMatrix | None = None
    imbalance: ForecastingMatrix | None = None
    power: ForecastingMatrix | None = None
    afrr_activated: Timeseries | None = None
    afrr_down_procured: Timeseries | None = None
    afrr_up_procured: Timeseries | None = None
    da_cleared_quantity: Timeseries | None = None
    fcr_activated: Timeseries | None = None
    imbalance_settlement_costs: Timeseries | None = None
    mfrr_activated: Timeseries | None = None
    mfrr_down_procured: Timeseries | None = None
    mfrr_up_procured: Timeseries | None = None
    rr_activated: Timeseries | None = None
    rr_down_procured: Timeseries | None = None
    rr_up_procured: Timeseries | None = None
    total_id_cleared_quantity: Timeseries | None = None
