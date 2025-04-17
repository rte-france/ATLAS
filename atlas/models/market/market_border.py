"""Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock
from atlas.models.market.market_area import MarketArea


class MarketBorder(BaseModel):
    """:param downhill_control_block: Downhill Control Block
    :type downhill_control_block: ControlBlock
    :param uphill_control_block: Uphill Control Block
    :type uphill_control_block: ControlBlock
    :param downhill_market_area: Downhill Market Area
    :type downhill_market_area: MarketArea
    :param uphill_market_area: Uphill Market Area
    :type uphill_market_area: MarketArea
    :param coupling_type: Sum of volume of sell offers on the Day Ahead market
    :type coupling_type: str
    :param loss_factor: Loss factor
    :type loss_factor: float
    :param time_resolution: Time resolution relative to the border
    :type time_resolution: float
    :param afrr_down_procured: Contractualization of downward AFRR crossing the border after Clearing
    :type afrr_down_procured: ForecastingMatrix
    :param afrr_up_procured: Contractualization of upward AFRR crossing the border after Clearing
    :type afrr_up_procured: ForecastingMatrix
    :param id_flow: Flows from the different Intraday Clearing
    :type id_flow: ForecastingMatrix
    :param id_shadow_price: Time resolution relative to the border
    :type id_shadow_price: float
    :param mfrr_down_procured: Contractualization of downward MFRR crossing the border after Clearing
    :type mfrr_down_procured: ForecastingMatrix
    :param mfrr_up_procured: Contractualization of upward MFRR crossing the border after Clearing
    :type mfrr_up_procured: ForecastingMatrix
    :param rr_down_procured: Contractualization of downward RR crossing the border after Clearing
    :type rr_down_procured: ForecastingMatrix
    :param rr_up_procured: Contractualization of upward RR crossing the border after Clearing
    :type rr_up_procured: ForecastingMatrix
    :param afrr_activated: Activated AFRR flow across the border
    :type afrr_activated: Timeseries
    :param da_flow: Flows from the different Day Ahead Clearing
    :type da_flow: Timeseries
    :param da_shadow_price: Shadow Price from the different Day Ahead Clearing
    :type da_shadow_price: Timeseries
    :param fcr_activated: Activated FCR flow across the border
    :type fcr_activated: Timeseries
    :param maximum_flow: Maximum flow across the border
    :type maximum_flow: Timeseries
    :param mfrr_activated: Activated MFRR flow across the border after MARI market
    :type mfrr_activated: Timeseries
    :param minimum_flow: Minimum flow across the border
    :type minimum_flow: Timeseries
    :param reference_flow: Reference flow across the border
    :type reference_flow: Timeseries
    :param rr_activated: Activated RR flow across the border after TERRE market
    :type rr_activated: Timeseries
    :param total_id_flow: Cumulative sum of accepted power from all Day Ahead Clearing
    :type total_id_flow: Timeseries
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    downhill_control_block: ControlBlock | None = None
    uphill_control_block: ControlBlock | None = None
    downhill_market_area: MarketArea | None = None
    uphill_market_area: MarketArea | None = None
    coupling_type: str | None = None
    loss_factor: float | None = None
    time_resolution: float | None = None  # Assuming this can be a float
    afrr_down_procured: ForecastingMatrix | None = None
    afrr_up_procured: ForecastingMatrix | None = None
    id_flow: ForecastingMatrix | None = None
    id_shadow_price: ForecastingMatrix | None = None
    mfrr_down_procured: ForecastingMatrix | None = None
    mfrr_up_procured: ForecastingMatrix | None = None
    rr_down_procured: ForecastingMatrix | None = None
    rr_up_procured: ForecastingMatrix | None = None
    afrr_activated: Timeseries | None = None
    da_flow: Timeseries | None = None
    da_shadow_price: Timeseries | None = None
    fcr_activated: Timeseries | None = None
    maximum_flow: Timeseries | None = None
    mfrr_activated: Timeseries | None = None
    minimum_flow: Timeseries | None = None
    reference_flow: Timeseries | None = None
    rr_activated: Timeseries | None = None
    total_id_flow: Timeseries | None = None
