"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel
from atlas.models.control_block import ControlBlock


class MarketArea(BusinessModel):
    """:param control_block: Associated Control block
    :type control_block: ControlBlock
    :param co2_emission: Stores CO2 emissions at the end of each Portfolio Optimization
    :type co2_emission: ForecastingMatrix | LazyForecastingMatrix
    :param id_balance: Net trading position of the zone on the various Intraday Clearing (sales - purchases)
    :type id_balance: ForecastingMatrix | LazyForecastingMatrix
    :param id_price: Prices from the Intraday clearing markets in the MarketArea
    :type id_price: ForecastingMatrix | LazyForecastingMatrix
    :param id_price_forecast: Sum of volume of sell offers on the Day Ahead market
    :type id_price_forecast: ForecastingMatrix | LazyForecastingMatrix
    :param price_forecast_high: High scenario of energy price forecasts for the various markets (ID, DA and Balancing)
    over the different deadlines
    :type price_forecast_high: ForecastingMatrix | LazyForecastingMatrix
    :param price_forecast_low: Low scenario of energy price forecasts for the various markets (ID, DA and Balancing)
    over the different deadlines
    :type price_forecast_low: ForecastingMatrix | LazyForecastingMatrix
    :param price_forecast_medium: Average scenario of energy price forecasts for the various markets
    (ID, DA and Balancing) over the different deadlines
    :type price_forecast_medium: ForecastingMatrix | LazyForecastingMatrix
    :param afrr_activation_price: Activation price of type AFRR (from MARI Clearing)
    :type afrr_activation_price: Timeseries | LazyTimeseries
    :param da_balance: Net trading position of the zone on the various Day Ahead Clearing (sales - purchases)
    :type da_balance: Timeseries | LazyTimeseries
    :param fcr_activation_price: Activation price of type FCR
    :type fcr_activation_price: Timeseries | LazyTimeseries
    :param maximum_price: Constraint added to price_groups in Clearing, during the price fixing phase
    :type maximum_price: Timeseries | LazyTimeseries
    :param minimum_price: Constraint added to price_groups in Clearing, during the price fixing phase
    :type minimum_price: Timeseries | LazyTimeseries
    :param mfrr_activation_balance: Net trade position of the zone after Clearing of MFRR reserves
    :type mfrr_activation_balance: Timeseries | LazyTimeseries
    :param mfrr_activation_price: Activation price of type MFRR
    :type mfrr_activation_price: Timeseries | LazyTimeseries
    :param reference_balance: Required to define flowbased constraints
    :type reference_balance: Timeseries | LazyTimeseries
    :param rr_activation_balance: Net trade position of the zone after Clearing of RR reserves
    :type rr_activation_balance: Timeseries | LazyTimeseries
    :param rr_activation_price: Activation price of type RR (from TERRE Clearing)
    :type rr_activation_price: Timeseries | LazyTimeseries
    :param total_id_balance: Cumulative sum of net trading position from all Intraday Clearing
    :type total_id_balance: Timeseries | LazyTimeseries
    """

    control_block: ControlBlock | None = None
    co2_emission: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_balance: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_price: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_price_forecast: ForecastingMatrix | LazyForecastingMatrix | None = None
    price_forecast_high: ForecastingMatrix | LazyForecastingMatrix | None = None
    price_forecast_low: ForecastingMatrix | LazyForecastingMatrix | None = None
    price_forecast_medium: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_activation_price: Timeseries | LazyTimeseries | None = None
    da_balance: Timeseries | LazyTimeseries | None = None
    fcr_activation_price: Timeseries | LazyTimeseries | None = None
    maximum_price: Timeseries | LazyTimeseries | None = None
    minimum_price: Timeseries | LazyTimeseries | None = None
    mfrr_activation_balance: Timeseries | LazyTimeseries | None = None
    mfrr_activation_price: Timeseries | LazyTimeseries | None = None
    reference_balance: Timeseries | LazyTimeseries | None = None
    rr_activation_balance: Timeseries | LazyTimeseries | None = None
    rr_activation_price: Timeseries | LazyTimeseries | None = None
    total_id_balance: Timeseries | LazyTimeseries | None = None
