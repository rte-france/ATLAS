"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel
from atlas.models.control_block import ControlBlock


class MarketArea(BusinessModel):
    """
    :param control_block: Associated Control block
    :type control_block: ControlBlock
    :param co2_emission: CO2 emissions at the end of each Portfolio Optimization
    :type co2_emission: ForecastingMatrix
    :param id_balance: Net position of the zone on the various Intraday market clearings (sales - purchases)
    :type id_balance: ForecastingMatrix
    :param id_price: Market area prices from each Intraday clearing market
    :type id_price: ForecastingMatrix
    :param id_price_forecast: Sum of volume of sell offers on the Day Ahead market
    :type id_price_forecast: ForecastingMatrix
    :param price_forecast_high: High price scenario of energy price forecasts for the various markets (ID, DA and
    Balancing) for different forecasting horizons
    over the different deadlines
    :type price_forecast_high: ForecastingMatrix
    :param price_forecast_low: Low price scenario of energy price forecasts for the various markets (ID, DA and
    Balancing) for different forecasting horizons
    over the different deadlines
    :type price_forecast_low: ForecastingMatrix
    :param price_forecast_medium: Medium price scenario of energy price forecasts for the various markets (ID, DA and
    Balancing) for different forecasting horizons
    (ID, DA and Balancing) over the different deadlines
    :type price_forecast_medium: ForecastingMatrix
    :param afrr_activation_price: Activation price of aFRR (from MARI Clearing)
    :type afrr_activation_price: Timeseries
    :param da_balance: Net position of the zone for the Day Ahead market clearing (sales - purchases)
    :type da_balance: Timeseries
    :param da_price: Market area prices from the Day Ahead clearing market
    :type da_price: Timeseries
    :param fcr_activation_price: Activation price of FCR
    :type fcr_activation_price: Timeseries
    :param maximum_price: Price cap for this market area
    :type maximum_price: Timeseries
    :param minimum_price: Minimum price allowed for this market area
    :type minimum_price: Timeseries
    :param mfrr_activation_balance: Net position of the zone after clearing of mFRR reserves
    :type mfrr_activation_balance: Timeseries
    :param mfrr_activation_price: Activation price of mFRR
    :type mfrr_activation_price: Timeseries
    :param reference_balance: Zonal reference net position in the base case. Used for the flow-based constraints
    :type reference_balance: Timeseries
    :param rr_activation_balance: Net position of the zone after clearing of RR reserves
    :type rr_activation_balance: Timeseries
    :param rr_activation_price: Activation price of RR (from TERRE Clearing)
    :type rr_activation_price: Timeseries
    :param total_id_balance: Cumulative sum of the net position from all Intraday market clearings
    :type total_id_balance: Timeseries
    """

    control_block: ControlBlock | None = None
    co2_emission: ForecastingMatrix | None = None
    id_balance: ForecastingMatrix | None = None
    id_price: ForecastingMatrix | None = None
    id_price_forecast: ForecastingMatrix | None = None
    price_forecast_high: ForecastingMatrix | None = None
    price_forecast_low: ForecastingMatrix | None = None
    price_forecast_medium: ForecastingMatrix | None = None
    afrr_activation_price: Timeseries | None = None
    da_balance: Timeseries | None = None
    da_price: Timeseries | None = None
    fcr_activation_price: Timeseries | None = None
    maximum_price: Timeseries | None = None
    minimum_price: Timeseries | None = None
    mfrr_activation_balance: Timeseries | None = None
    mfrr_activation_price: Timeseries | None = None
    reference_balance: Timeseries | None = None
    rr_activation_balance: Timeseries | None = None
    rr_activation_price: Timeseries | None = None
    total_id_balance: Timeseries | None = None
