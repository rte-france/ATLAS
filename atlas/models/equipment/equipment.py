"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic import Field

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.scenario_matrix import LazyScenarioMatrix, ScenarioMatrix
from atlas.math.timeseries import Timeseries
from atlas.models.business_model import BusinessModel
from atlas.models.node import Node
from atlas.models.portfolio import Portfolio


class Equipment(BusinessModel):
    """:param node: Associated Node
    :type node: Node
    :param portfolio: Associated Portfolio
    :type portfolio: Portfolio
    :param coe2_emission_factor: CO2 emissions per MWh
    :type coe2_emission_factor: float
    :param has_daily_energy_constraint: True if equipment has a storage limit, False otherwise
    :type has_daily_energy_constraint: bool
    :param maximum_afrr: Maximum volume that can be allocated to aFRR
    :type maximum_afrr: float
    :param maximum_fcr: Maximum volume that can be allocated to FCR
    :type maximum_fcr: float
    :param maximum_gradient: Maximum gradient possible with 0 representing an infinite gradient
    :type maximum_gradient: float
    :param setup_delay: Time between the transmission of an activation order and the respective production change of a
    unit. Currently used for balancing time frames.
    :type setup_delay: float
    :param unit_count: Number of units in the cluster
    :type unit_count: float
    :param afrr_down_procured: Volume of contracted downward aFRR reserves
    :type afrr_down_procured: ForecastingMatrix
    :param afrr_up_procured: Volume of contracted upward aFRR reserves
    :type afrr_up_procured: ForecastingMatrix
    :param fcr_down_procured: Volume of contracted downward FCR reserves
    :type fcr_down_procured: ForecastingMatrix
    :param fcr_up_procured: Volume of contracted upward FCR reserves
    :type fcr_up_procured: ForecastingMatrix
    :param mfrr_down_procured: Volume of contracted downward mFRR reserves
    :type mfrr_down_procured: ForecastingMatrix
    :param mfrr_up_procured: Volume of contracted upward mFRR reserves
    :type mfrr_up_procured: ForecastingMatrix
    :param rr_down_procured: Volume of contracted downward RR reserves
    :type rr_down_procured: ForecastingMatrix
    :param rr_up_procured: Volume of contracted upward RR reserves
    :type rr_up_procured: ForecastingMatrix
    :param co2_emission_factor: CO2 emissions per MWh
    :type co2_emission_factor: float
    :param co2_emissions: Cumulated CO2 emission after Portfolio Optimization
    :type co2_emissions: ForecastingMatrix
    :param id_buy_submitted_volume: Sum of volume of buy offers for each Intraday market
    :type id_buy_submitted_volume: ForecastingMatrix
    :param id_cleared_quantity: Total quantity accepted in each Intraday market. Represents the sum of accepted powers
    of all orders for this equipment
    :type id_cleared_quantity: ForecastingMatrix
    :param id_po_for_orders: Intermediate result of Portfolio optimization for Intraday market.
    Note that this value does not represent the production plan of the unit, but rather an intermediate result used
    for the creation of intraday orders.
    :type id_po_for_orders: ForecastingMatrix
    :param id_sell_submitted_volume: Sum of volume of sell offers for each Intraday market
    :type id_sell_submitted_volume: ForecastingMatrix
    :param power: Production schedules for each hour and for each time horizon
    :type power: ForecastingMatrix
    :param specific_activated_power: Power activated by the Balancing Mechanism
    :type specific_activated_power: ForecastingMatrix
    :param storage_marginal_value: Storage use value. Ex: Water value for hydraulic equipment
    :type storage_marginal_value: ScenarioMatrix
    :param afrr_activated: Volume of aFRR activated
    :type afrr_activated: Timeseries
    :param afrr_submitted_volume: To be modified, in this state this property does not describe anything properly
    :type afrr_submitted_volume: Timeseries
    :param mfrr_activated: Volume of mFRR activated
    :type mfrr_activated: Timeseries
    :param mfrr_submitted_volume: To be modified, in this state this property does not describe anything properly
    :type mfrr_submitted_volume: Timeseries
    :param fcr_activated: Volume of FCR activated
    :type fcr_activated: Timeseries
    :param fcr_submitted_volume: To be modified, in this state this property does not describe anything properly
    :type fcr_submitted_volume: Timeseries
    :param rr_activated: Volume of RR activated
    :type rr_activated: Timeseries
    :param rr_submitted_volume: To be modified, in this state this property does not describe anything properly
    :type rr_submitted_volume: Timeseries
    :param da_cleared_quantity: Sum of accepted power by day-ahead market
    :type da_cleared_quantity: Timeseries | LazyTimeseries
    :param maximum_daily_energy: Maximum daily quantity of energy that can be produced
    :type maximum_daily_energy: Timeseries | LazyTimeseries
    :param minimum_daily_energy: Minimum daily quantity of energy that can be produced
    :type minimum_daily_energy: Timeseries
    :param startup_cost: Startup cost. Currently only used for thermic equipment class. If the equipment represents
    a cluster of units, this value is the start-up cost per unit.
    :type startup_cost: Timeseries
    :param total_id_buy_submitted_volume: Sum of volume of buy offers for each Intraday market
    :type total_id_buy_submitted_volume: Timeseries
    :param total_id_cleared_quantity: Cumulative sum of all accepted power from all Intraday clearing
    :type total_id_cleared_quantity: Timeseries
    :param total_id_sell_submitted_volume: Cumulative sum of sell offers from all Intraday markets
    :type total_id_sell_submitted_volume: Timeseries
    :param variable_cost: Variable cost
    :type variable_cost: Timeseries | LazyTimeseries
    """

    node: Node | None = Field(None, description="Class Business model Node")
    portfolio: Portfolio | None = Field(None, description="Class Business model Portfolio")
    coe2_emission_factor: float | None = Field(None, description="COE2 emission factor")
    has_daily_energy_constraint: bool | None = None
    maximum_afrr: float | None = None
    maximum_fcr: float | None = None
    maximum_gradient: float | None = None
    setup_delay: float | None = Field(None, ge=0, description="Setup delay (must be positive)")
    unit_count: int | None = Field(None, ge=0, description="Unit count (must be positive)")
    afrr_down_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    co2_emission_factor: float | None = Field(None, ge=0)
    co2_emissions: ForecastingMatrix | LazyForecastingMatrix | None = None
    fcr_down_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    fcr_up_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_buy_submitted_volume: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_cleared_quantity: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_po_for_orders: ForecastingMatrix | LazyForecastingMatrix | None = None
    id_sell_submitted_volume: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_down_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    mfrr_up_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    power: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_down_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    rr_up_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    specific_activated_power: ForecastingMatrix | LazyForecastingMatrix | None = None
    storage_marginal_value: ScenarioMatrix | LazyScenarioMatrix | None = None
    afrr_activated: Timeseries | LazyTimeseries | None = None
    afrr_submitted_volume: Timeseries | LazyTimeseries | None = None
    mfrr_activated: Timeseries | LazyTimeseries | None = None
    mfrr_submitted_volume: Timeseries | LazyTimeseries | None = None
    fcr_activated: Timeseries | LazyTimeseries | None = None
    fcr_submitted_volume: Timeseries | LazyTimeseries | None = None
    rr_activated: Timeseries | LazyTimeseries | None = None
    rr_submitted_volume: Timeseries | LazyTimeseries | None = None
    da_cleared_quantity: Timeseries | LazyTimeseries | None = None
    maximum_daily_energy: Timeseries | LazyTimeseries | None = None
    minimum_daily_energy: Timeseries | LazyTimeseries | None = None
    startup_cost: Timeseries | LazyTimeseries | None = None
    total_id_buy_submitted_volume: Timeseries | LazyTimeseries | None = None
    total_id_cleared_quantity: Timeseries | LazyTimeseries | None = None
    total_id_sell_submitted_volume: Timeseries | LazyTimeseries | None = None
    variable_cost: Timeseries | LazyTimeseries | None = None
