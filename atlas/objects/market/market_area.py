"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import field_serializer

from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.business_model import BusinessModel
from atlas.objects.network_operator.control_block import ControlBlock
from atlas.validators import serializer_business_model


class MarketArea(BusinessModel):
    """
    :param control_block: Associated Control block
    :type control_block: ControlBlock
    :param co2_emissions: CO2 emissions at the end of each Portfolio Optimization
    :type co2_emissions: ForecastingMatrix
    :param id_balance: Net position of the zone on the various Intraday market clearings (sales - purchases)
    :type id_balance: ForecastingMatrix
    :param id_price: Market area prices from each Intraday clearing market
    :type id_price: ForecastingMatrix
    :param id_price_forecast: Sum of volume of sell offers on the Day Ahead market
    :type id_price_forecast: ForecastingMatrix
    :param price_forecast_high: High price scenario of energy price forecasts for the various markets (ID, DA and
    Balancing) for different forecasting horizons over the different deadlines
    :type price_forecast_high: ForecastingMatrix
    :param price_forecast_low: Low price scenario of energy price forecasts for the various markets (ID, DA and
    Balancing) for different forecasting horizons over the different deadlines
    :type price_forecast_low: ForecastingMatrix
    :param price_forecast_medium: Medium price scenario of energy price forecasts for the various markets (ID, DA and
    Balancing) for different forecasting horizons (ID, DA and Balancing) over the different deadlines
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
    co2_emissions: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_balance: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_price: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_price_forecast: ForecastingMatrix | LazyForecastingMatrix | None = None
    price_forecast_high: ForecastingMatrix | LazyForecastingMatrix | None = None
    price_forecast_low: ForecastingMatrix | LazyForecastingMatrix | None = None
    price_forecast_medium: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_activation_price: AbstractTimeseries | None = None
    da_balance: AbstractTimeseries | None = None
    da_price: AbstractTimeseries | None = None
    fcr_activation_price: AbstractTimeseries | None = None
    maximum_price: AbstractTimeseries | None = None
    minimum_price: AbstractTimeseries | None = None
    mfrr_activation_balance: AbstractTimeseries | None = None
    mfrr_activation_price: AbstractTimeseries | None = None
    reference_balance: AbstractTimeseries | None = None
    rr_activation_balance: AbstractTimeseries | None = None
    rr_activation_price: AbstractTimeseries | None = None
    total_id_balance: AbstractTimeseries | None = None

    @field_serializer("control_block", mode="plain")
    def serializer_bmo(self, value: BusinessModel | None) -> str | None:
        """Serialize BusinessModel attributes to string."""
        return serializer_business_model(value)
