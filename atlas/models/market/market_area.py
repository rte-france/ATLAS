"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import BaseModel, ConfigDict

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.control_block import ControlBlock


class MarketArea(BaseModel):
    """:param control_block: Associated Control block
    :type control_block: ControlBlock
    :param co2_emission: Stores CO2 emissions at the end of each Portfolio Optimization
    :type co2_emission: ForecastingMatrix
    :param id_balance: Net trading position of the zone on the various Intraday Clearing (sales - purchases)
    :type id_balance: ForecastingMatrix
    :param id_price: Prices from the Intraday clearing markets in the MarketArea
    :type id_price: ForecastingMatrix
    :param id_price_forecast: Sum of volume of sell offers on the Day Ahead market
    :type id_price_forecast: ForecastingMatrix
    :param price_forecast_high: High scenario of energy price forecasts for the various markets (ID, DA and Balancing)
    over the different deadlines
    :type price_forecast_high: ForecastingMatrix
    :param price_forecast_low: Low scenario of energy price forecasts for the various markets (ID, DA and Balancing)
    over the different deadlines
    :type price_forecast_low: ForecastingMatrix
    :param price_forecast_medium: Average scenario of energy price forecasts for the various markets
    (ID, DA and Balancing) over the different deadlines
    :type price_forecast_medium: ForecastingMatrix
    :param afrr_activation_price: Activation price of type AFRR (from MARI Clearing)
    :type afrr_activation_price: Timeseries
    :param da_balance: Net trading position of the zone on the various Day Ahead Clearing (sales - purchases)
    :type da_balance: Timeseries
    :param fcr_activation_price: Activation price of type FCR
    :type fcr_activation_price: Timeseries
    :param maximum_price: Constraint added to price_groups in Clearing, during the price fixing phase
    :type maximum_price: Timeseries
    :param minimum_price: Constraint added to price_groups in Clearing, during the price fixing phase
    :type minimum_price: Timeseries
    :param mfrr_activation_balance: Net trade position of the zone after Clearing of MFRR reserves
    :type mfrr_activation_balance: Timeseries
    :param mfrr_activation_price: Activation price of type MFRR
    :type mfrr_activation_price: Timeseries
    :param reference_balance: Required to define flowbased constraints
    :type reference_balance: Timeseries
    :param rr_activation_balance: Net trade position of the zone after Clearing of RR reserves
    :type rr_activation_balance: Timeseries
    :param rr_activation_price: Activation price of type RR (from TERRE Clearing)
    :type rr_activation_price: Timeseries
    :param total_id_balance: Cumulative sum of net trading position from all Intraday Clearing
    :type total_id_balance: Timeseries
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
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
    fcr_activation_price: Timeseries | None = None
    maximum_price: Timeseries | None = None
    minimum_price: Timeseries | None = None
    mfrr_activation_balance: Timeseries | None = None
    mfrr_activation_price: Timeseries | None = None
    reference_balance: Timeseries | None = None
    rr_activation_balance: Timeseries | None = None
    rr_activation_price: Timeseries | None = None
    total_id_balance: Timeseries | None = None
