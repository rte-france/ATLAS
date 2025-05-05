"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.enum import ReservesTypes
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel


class ControlBlock(BusinessModel):
    """:param alternative_type: Type of alternative considered for formulating a TSO offer on a balancing market
    :type alternative_type: ReservesTypes
    :param volume_uncertainty: True if uncertainty about the volume of the TSO's balancing requirement must be taken
    into account when formulating bids on a balancing market
    :type volume_uncertainty: bool
    :param affr_down_required: Need of downward AFRR contract to meet ControlBlock supply criteria
    :type affr_down_required: ForecastingMatrix | LazyForecastingMatrix
    :param affr_up_required: Need of upward AFRR contract to meet ControlBlock supply criteria
    :type affr_up_required: ForecastingMatrix | LazyForecastingMatrix
    :param balancing_mechanism_needs: Balancing needs for the Balancing Mechanism
    :type balancing_mechanism_needs: ForecastingMatrix | LazyForecastingMatrix
    :param mfrr_down_required: Need of downward MFRR contract to meet ControlBlock supply criteria
    :type mfrr_down_required: ForecastingMatrix | LazyForecastingMatrix
    :param mfrr_needs: Balancing needs for MFRR reserves
    :type mfrr_needs: ForecastingMatrix | LazyForecastingMatrix
    :param mfrr_up_required: Need of upward MFRR contract to meet ControlBlock supply criteria
    :type mfrr_up_required: ForecastingMatrix | LazyForecastingMatrix
    :param rr_down_required: Need of downward RR contract to meet ControlBlock supply criteria
    :type rr_down_required: ForecastingMatrix | LazyForecastingMatrix
    :param rr_needs: Balancing needs for RR reserves
    :type rr_needs: ForecastingMatrix | LazyForecastingMatrix
    :param rr_up_required: Need of upward RR contract to meet ControlBlock supply criteria
    :type rr_up_required: ForecastingMatrix | LazyForecastingMatrix
    :param spilled_energy: Energy lost (due to uncapped overproduction)
    :type spilled_energy: ForecastingMatrix | LazyForecastingMatrix
    :param unsupplied_energy: Energy not distributed in real time, after balancing processes
    :type unsupplied_energy: ForecastingMatrix | LazyForecastingMatrix
    :param afrr_activation_costs: Balancing costs for AFRR reserves
    :type afrr_activation_costs: Timeseries | LazyTimeseries
    :param fcr_activation_costs: Balancing costs for FCR reserves
    :type fcr_activation_costs: Timeseries | LazyTimeseries
    :param mfrr_activated: Volume of MFRR activated
    :type mfrr_activated: Timeseries | LazyTimeseries
    :param mfrr_activation_costs: Balancing costs for MFRR reserves
    :type mfrr_activation_costs: Timeseries | LazyTimeseries
    :param negative_imbalance_price: Settlement price for negative imbalance
    :type negative_imbalance_price: Timeseries | LazyTimeseries
    :param positive_imbalance_price: Settlement price for positive imbalance
    :type positive_imbalance_price: Timeseries | LazyTimeseries
    :param rr_activated: Volume of RR activated
    :type rr_activated: Timeseries | LazyTimeseries
    :param rr_activation_costs: Balancing costs for RR reserves
    :type rr_activation_costs: Timeseries | LazyTimeseries
    :param specific_activated: Volume of specific activated
    :type specific_activated: Timeseries | LazyTimeseries
    :param specific_activation_costs: Balancing total cost after the Balancing Mechanism
    :type specific_activation_costs: Timeseries | LazyTimeseries
    :param weighted_balance_price_down: Weighted average balancing energy activation price downward
    :type weighted_balance_price_down: Timeseries | LazyTimeseries
    :param weighted_balance_price_up: Weighted average balancing energy activation price upward
    :type weighted_balance_price_up: Timeseries | LazyTimeseries
    """

    alternative_type: ReservesTypes | None = None
    volume_uncertainty: bool | None = None
    affr_down_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    affr_up_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    balancing_mechanism_needs: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_down_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_needs: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_up_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_down_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_needs: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_up_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    spilled_energy: ForecastingMatrix | LazyForecastingMatrix | None = None
    unsupplied_energy: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_activation_costs: Timeseries | LazyTimeseries | None = None
    fcr_activation_costs: Timeseries | LazyTimeseries | None = None
    mfrr_activated: Timeseries | LazyTimeseries | None = None
    mfrr_activation_costs: Timeseries | LazyTimeseries | None = None
    negative_imbalance_price: Timeseries | LazyTimeseries | None = None
    positive_imbalance_price: Timeseries | LazyTimeseries | None = None
    rr_activated: Timeseries | LazyTimeseries | None = None
    rr_activation_costs: Timeseries | LazyTimeseries | None = None
    specific_activated: Timeseries | LazyTimeseries | None = None
    specific_activation_costs: Timeseries | LazyTimeseries | None = None
    weighted_balance_price_down: Timeseries | LazyTimeseries | None = None
    weighted_balance_price_up: Timeseries | LazyTimeseries | None = None
