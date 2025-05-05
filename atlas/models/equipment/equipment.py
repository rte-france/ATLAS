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


class Equipment(BusinessModel):
    """:param node: Associated Node
    :type node: Node
    :param portfolio: Associated Portfolio
    :type portfolio: Portfolio
    :param coe2_emission_factor: CO2 emitted per MWh
    :type coe2_emission_factor: float
    :param has_daily_energy_constraint: True if equipment is avaiblable, False otherwise
    :type has_daily_energy_constraint: bool
    :param maximum_afrr: Maximum volume allocable to AFRR
    :type maximum_afrr: float
    :param maximum_fcr: Maximum volume allocable to fcr
    :type maximum_fcr: float
    :param maximum_gradient: Maximum gradient for equipment with 0 as infinite gradient
    :type maximum_gradient: float
    :param setup_delay: Time between activation order transmission and power update of a group
    :type setup_delay: float
    :param unit_count: Aggregated number of unit
    :type unit_count: float
    :param afrr_down_procured: Volume of AFRR reserves contracted downward
    :type afrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    :param afrr_up_procured: Volume of AFRR reserves contracted upward
    :type afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    :param fcr_down_procured: Volume of FCR reserves contracted downward
    :type fcr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    :param fcr_up_procured: Volume of FCR reserves contracted upward
    :type fcr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    :param mfrr_down_procured: Volume of MFRR reserves contracted downward
    :type mfrr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    :param mfrr_up_procured: Volume of MFRR reserves contracted upward
    :type mfrr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    :param rr_down_procured: Volume of RR reserves contracted downward
    :type rr_down_procured: ForecastingMatrix | LazyForecastingMatrix
    :param rr_up_procured: Volume of RR reserves contracted upward
    :type rr_up_procured: ForecastingMatrix | LazyForecastingMatrix
    :param co2_emissions: Cumulated CO2 emission after Portfolio optimization
    :type co2_emissions: ForecastingMatrix | LazyForecastingMatrix
    :param id_buy_submitted_volume: Sum of buy offers volume proposed for Intraday market
    :type id_buy_submitted_volume: ForecastingMatrix | LazyForecastingMatrix
    :param id_cleared_quantity: Sum of accepted powers of orders for Intraday market
    :type id_cleared_quantity: ForecastingMatrix | LazyForecastingMatrix
    :param id_po_for_orders: Intermediate result of Portfolio optimization for Intraday market
    :type id_po_for_orders: ForecastingMatrix | LazyForecastingMatrix
    :param id_sell_submitted_volume: Sum of sell offers volume proposed for Intraday market
    :type id_sell_submitted_volume: ForecastingMatrix | LazyForecastingMatrix
    :param power: Production schedules for each hour and for each deadline
    :type power: ForecastingMatrix | LazyForecastingMatrix
    :param specific_activated_power: Power activated by the Balancing Mechanism, for balancing purposes
    :type specific_activated_power: ForecastingMatrix | LazyForecastingMatrix
    :param storage_marginal_value: Use value. Ex: Use value of water for hydraulic equipment
    :type storage_marginal_value: ScenarioMatrix | LazyScenarioMatrix
    :param afrr_activated: Volume of AFRR activated
    :type afrr_activated: Timeseries | LazyTimeseries
    :param afrr_submitted_volume: No documentation
    :type afrr_submitted_volume: Timeseries | LazyTimeseries
    :param mfrr_activated: Volume of MFRR activated
    :type mfrr_activated: Timeseries | LazyTimeseries
    :param mfrr_submitted_volume: No documentation
    :type mfrr_submitted_volume: Timeseries | LazyTimeseries
    :param fcr_activated: Volume of FCR activated
    :type fcr_activated: Timeseries | LazyTimeseries
    :param fcr_submitted_volume: No documentation
    :type fcr_submitted_volume: Timeseries | LazyTimeseries
    :param rr_activated: Volume of RR activated
    :type rr_activated: Timeseries | LazyTimeseries
    :param rr_submitted_volume: No documentation
    :type rr_submitted_volume: Timeseries | LazyTimeseries
    :param da_cleared_quantity: Sum of accepted power by day-ahead market
    :type da_cleared_quantity: Timeseries | LazyTimeseries
    :param maximum_daily_energy: Maximum daily quantity of energy that can be produced
    :type maximum_daily_energy: Timeseries | LazyTimeseries
    :param minimum_daily_energy: Minimum daily quantity of energy that can be produced
    :type minimum_daily_energy: Timeseries | LazyTimeseries
    :param startup_cost: Startup cost. Only used for Thermal Equipment
    :type startup_cost: Timeseries | LazyTimeseries
    :param total_id_buy_submitted_volume: Cumulative sum of buy offers from all Intraday market
    :type total_id_buy_submitted_volume: Timeseries | LazyTimeseries
    :param total_id_cleared_quantity: Cumulative sum of all accepted power from all Intraday clearing
    :type total_id_cleared_quantity: Timeseries | LazyTimeseries
    :param total_id_sell_submitted_volume: Cumulative sum of sell offers from all Intraday market
    :type total_id_sell_submitted_volume: Timeseries | LazyTimeseries
    :param variable_cost: Variable cost
    :type variable_cost: Timeseries | LazyTimeseries
    """

    node: str | None = Field(None, description="Class Business model Node")
    portfolio: str | None = Field(None, description="Class Business model Portfolio")
    coe2_emission_factor: float | None = Field(None, description="COE2 emission factor")
    has_daily_energy_constraint: bool | None = None
    maximum_afrr: float | None = None
    maximum_fcr: float | None = None
    maximum_gradient: float | None = None
    setup_delay: float | None = Field(None, ge=0, description="Setup delay (must be positive)")
    unit_count: int | None = Field(None, ge=0, description="Unit count (must be positive)")
    afrr_down_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
    afrr_up_procured: ForecastingMatrix | LazyForecastingMatrix | None = None
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
