"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import timedelta
from typing import Any

from pendulum import Duration
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    model_serializer,
    model_validator,
)

from atlas.enums import MarketType
from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
from atlas.math.abstract_timeseries import AbstractTimeseries
from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.objects.business_model import BusinessModel
from atlas.objects.market_operator.portfolio import Portfolio
from atlas.objects.network.node import Node
from atlas.validators import BusinessModelRef, DurationField

_DURATION_ADAPTER: TypeAdapter[timedelta] = TypeAdapter(timedelta)


def _duration_to_iso(value: timedelta) -> str:
    return _DURATION_ADAPTER.dump_python(value, mode="json")


class AdditionalHours(BaseModel):
    """
    Extra hours appended to the optimisation window, per market time frame.

    Can be built from a single duration (applied to every time frame) or from a
    ``key=duration`` string separated by ``|``, which is also the CSV representation.

    :param day_ahead: Additional hours for the day-ahead market
    :type day_ahead: Duration
    :param intraday: Additional hours for the intraday market
    :type intraday: Duration
    :param rr_activation: Additional hours for RR activation
    :type rr_activation: Duration
    :param mfrr_activation: Additional hours for mFRR activation
    :type mfrr_activation: Duration
    :param specific_activation: Additional hours for specific activation
    :type specific_activation: Duration

    Example::

        >>> AdditionalHours.model_validate("PT12H").intraday
        Duration(hours=12)
        >>> hours = AdditionalHours.model_validate("day_ahead=PT12H|intraday=PT6H")
        >>> hours.for_market(MarketType.intraday)
        Duration(hours=6)
        >>> hours.model_dump(mode="json")
        'day_ahead=PT12H|intraday=PT6H'
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    day_ahead: DurationField | None = None
    intraday: DurationField | None = None
    rr_activation: DurationField | None = None
    mfrr_activation: DurationField | None = None
    specific_activation: DurationField | None = None

    @classmethod
    def uniform(cls, duration: Duration) -> "AdditionalHours":
        """
        Build an instance with the same duration for every time frame.

        :param duration: Duration applied to every time frame
        :type duration: Duration
        :return: Instance with every time frame set to ``duration``
        :rtype: AdditionalHours
        """
        return cls(**dict.fromkeys(cls.model_fields, duration))

    @model_validator(mode="before")
    @classmethod
    def _parse(cls, value: Any) -> Any:
        if isinstance(value, timedelta):
            return dict.fromkeys(cls.model_fields, value)
        if not isinstance(value, str):
            return value
        if "=" not in value:
            return dict.fromkeys(cls.model_fields, value.strip())
        parsed: dict[str, str] = {}
        for item in value.split("|"):
            key, separator, duration = item.partition("=")
            key = key.strip()
            if not separator:
                raise ValueError(f"Invalid additional hours item '{item}', expected 'key=duration'")
            if key in parsed:
                raise ValueError(f"Duplicate additional hours key '{key}'")
            parsed[key] = duration.strip()
        return parsed

    @model_serializer(mode="wrap")
    def _serialize(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> Any:
        if not info.mode_is_json():
            return handler(self)
        values = {name: getattr(self, name) for name in type(self).model_fields}
        defined = {name: value for name, value in values.items() if value is not None}
        if not defined:
            return None
        if len(defined) == len(values) and len(set(defined.values())) == 1:
            return _duration_to_iso(next(iter(defined.values())))
        return "|".join(f"{name}={_duration_to_iso(value)}" for name, value in defined.items())

    def for_market(self, market: MarketType) -> Duration | None:
        """
        Return the additional hours of the time frame matching a market type.

        :param market: Market type
        :type market: MarketType
        :return: Additional hours for this market, ``None`` if not defined
        :rtype: Duration | None
        """
        return getattr(self, _MARKET_TO_FIELD[market])

    def fill_missing(self, default: Duration) -> "AdditionalHours":
        """
        Return a copy where every undefined time frame is set to ``default``.

        :param default: Duration used for undefined time frames
        :type default: Duration
        :return: Completed copy
        :rtype: AdditionalHours
        """
        return self.model_copy(
            update={name: default for name in type(self).model_fields if getattr(self, name) is None}
        )


_MARKET_TO_FIELD: dict[MarketType, str] = {
    MarketType.dayahead: "day_ahead",
    MarketType.intraday: "intraday",
    MarketType.rr_activation: "rr_activation",
    MarketType.mfrr_activation: "mfrr_activation",
}


class Equipment(BusinessModel):
    """
    :param node: Associated Node
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
    Note that this value does not represent the production plan of the unit, but rather an intermediate result used for the creation of intraday orders.
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
    :type da_cleared_quantity: AbstractTimeseries
    :param maximum_daily_energy: Maximum daily quantity of energy that can be produced
    :type maximum_daily_energy: AbstractTimeseries
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
    :type variable_cost: AbstractTimeseries
    :param long_term_markets_commitment: Generation or consumption sold in long term markets (MW)
    :type long_term_markets_commitment: Timeseries
    :param antares_min_gen: Minimum generation level imposed within the Antares simulation (MW)
    :type antares_min_gen: Timeseries
    :param antares_dispatch: Output dispatch of an Antares simulation (MW)
    :type antares_dispatch: Timeseries
    :param additional_hours: Extra hours appended to the optimisation window, per market time frame
    :type additional_hours: AdditionalHours
    """

    node: BusinessModelRef[Node]
    portfolio: BusinessModelRef[Portfolio]
    co2_emission_factor: float | None = Field(None, description="COE2 emission factor")
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
    storage_marginal_value: AbstractScenarioMatrix | None = None
    afrr_activated: AbstractTimeseries | None = None
    afrr_submitted_volume: AbstractTimeseries | None = None
    mfrr_activated: AbstractTimeseries | None = None
    mfrr_submitted_volume: AbstractTimeseries | None = None
    fcr_activated: AbstractTimeseries | None = None
    fcr_submitted_volume: AbstractTimeseries | None = None
    rr_activated: AbstractTimeseries | None = None
    rr_submitted_volume: AbstractTimeseries | None = None
    da_cleared_quantity: AbstractTimeseries | None = None
    maximum_daily_energy: AbstractTimeseries | None = None
    minimum_daily_energy: AbstractTimeseries | None = None
    startup_cost: AbstractTimeseries | None = None
    total_id_buy_submitted_volume: AbstractTimeseries | None = None
    total_id_cleared_quantity: AbstractTimeseries | None = None
    total_id_sell_submitted_volume: AbstractTimeseries | None = None
    variable_cost: AbstractTimeseries | None = None

    additional_hours: AdditionalHours | None = None
    antares_min_gen: AbstractTimeseries | None = None
    antares_dispatch: AbstractTimeseries | None = None
    long_term_markets_commitment: AbstractTimeseries | None = None
