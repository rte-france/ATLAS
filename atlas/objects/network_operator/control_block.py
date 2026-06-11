"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.core.math.abstract_timeseries import AbstractTimeseries
from atlas.core.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.enums import ReservesTypes
from atlas.objects.business_model import BusinessModel


class ControlBlock(BusinessModel):
    """
    :param alternative_type: Type of alternative considered for formulating a TSO offer on a balancing market
    :type alternative_type: ReservesTypes
    :param volume_uncertainty: True if uncertainty about the volume of the TSO's balancing requirement must be taken
    into account when formulating bids on a balancing market
    :type volume_uncertainty: bool
    :param afrr_down_required: Procurement need of downward aFRR for this Control Block
    :type afrr_down_required: ForecastingMatrix
    :param afrr_up_required: Procurement Need of upward aFRR for this Control Block
    :type afrr_up_required: ForecastingMatrix
    :param balancing_mechanism_needs: Balancing needs for the Balancing Mechanism
    :type balancing_mechanism_needs: ForecastingMatrix
    :param mfrr_down_required: Procurement need of downward mFRR for this Control Block
    :type mfrr_down_required: ForecastingMatrix
    :param mfrr_needs: Balancing needs for mFRR reserves
    :type mfrr_needs: ForecastingMatrix
    :param mfrr_up_required: Procurement need of upward mFRR for this Control Block
    :type mfrr_up_required: ForecastingMatrix
    :param rr_down_required: Procurement need of downward RR for this Control Block
    :type rr_down_required: ForecastingMatrix
    :param rr_needs: Balancing needs for RR reserves
    :type rr_needs: ForecastingMatrix
    :param rr_up_required: Procurement need of upward RR for this Control Block
    :type rr_up_required: ForecastingMatrix
    :param spilled_energy: Energy lost (due to uncapped overproduction)
    :type spilled_energy: ForecastingMatrix | LazyForecastingMatrix
    :param unsupplied_energy: Energy not distributed in real time, after balancing processes
    :type unsupplied_energy: ForecastingMatrix
    :param afrr_activation_costs: Balancing costs for aFRR reserves
    :type afrr_activation_costs: Timeseries
    :param fcr_activation_costs: Balancing costs for FCR reserves
    :type fcr_activation_costs: Timeseries
    :param mfrr_activated: Volume of mFRR activated
    :type mfrr_activated: Timeseries
    :param mfrr_activation_costs: Balancing costs for mFRR reserves
    :type mfrr_activation_costs: Timeseries
    :param negative_imbalance_price: Negative Imbalance Settlement Price (ISP-N)
    :type negative_imbalance_price: Timeseries
    :param positive_imbalance_price: Positive Imbalance Settlement Price (ISP-P)
    :type positive_imbalance_price: Timeseries
    :param rr_activated: Volume of RR activated
    :type rr_activated: AbstractTimeseries
    :param rr_activation_costs: Balancing costs for RR reserves
    :type rr_activation_costs: Timeseries
    :param specific_activated_power: Power activated by the Balancing Mechanism
    :type specific_activated_power: Timeseries
    :param specific_activation_costs: Total balancing cost from the Balancing Mechanism
    :type specific_activation_costs: Timeseries
    :param weighted_balance_price_down: Weighted average balancing energy activation price downward
    :type weighted_balance_price_down: AbstractTimeseries
    :param weighted_balance_price_up: Weighted average balancing energy activation price upward
    :type weighted_balance_price_up: AbstractTimeseries
    """

    alternative_type: ReservesTypes | None = None
    volume_uncertainty: bool | None = None
    afrr_down_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_up_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    balancing_mechanism_needs: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_down_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_needs: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_up_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_down_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_needs: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_up_required: ForecastingMatrix | LazyForecastingMatrix | None = None
    spilled_energy: ForecastingMatrix | LazyForecastingMatrix | None = None
    unsupplied_energy: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_activation_costs: AbstractTimeseries | None = None
    fcr_activation_costs: AbstractTimeseries | None = None
    mfrr_activated: AbstractTimeseries | None = None
    mfrr_activation_costs: AbstractTimeseries | None = None
    negative_imbalance_price: AbstractTimeseries | None = None
    positive_imbalance_price: AbstractTimeseries | None = None
    rr_activated: AbstractTimeseries | None = None
    rr_activation_costs: AbstractTimeseries | None = None
    weighted_balance_price_down: AbstractTimeseries | None = None
    weighted_balance_price_up: AbstractTimeseries | None = None
    specific_activated_power: AbstractTimeseries | None = None
    specific_activation_costs: AbstractTimeseries | None = None
