from typing import cast

from pendulum import DateTime

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.models.equipment.equipment import Equipment
from atlas.models.equipment.hydro import Hydro
from atlas.models.equipment.load import Load
from atlas.models.equipment.other_non_dispatchable import OtherNonDispatchable
from atlas.models.equipment.solar import Solar
from atlas.models.equipment.storage import Storage
from atlas.models.equipment.wind import Wind
from atlas.models.portfolio import Portfolio
from atlas.modules.portfolio_optimisation.parameters import MarketEnum, PortfolioOptimisationParameters


def get_price_forecast(portfolio: Portfolio, time: DateTime, parameters: PortfolioOptimisationParameters) -> float:
    """Get price forecast for given time based on market type and forecast settings."""

    if time in parameters.target_times:
        if parameters.use_forecast:
            if parameters.market == MarketEnum.dayahead:
                return portfolio.market_area.price_forecast_medium.get_value(time)
            elif parameters.market == MarketEnum.intraday:
                return portfolio.market_area.id_price_forecast.get_forecast(
                    parameters.execution_date, time, time
                ).get_value(time)

        else:
            if parameters.market == MarketEnum.dayahead:
                return portfolio.market_area.da_price.get_value(time)
            elif parameters.market == MarketEnum.intraday:
                return portfolio.market_area.id_price.get_forecast(parameters.execution_date, time, time).get_value(
                    time
                )
            elif parameters.market == MarketEnum.rr_activation:
                return portfolio.market_area.rr_activation_price.get_value(time)
            elif parameters.market == MarketEnum.mfrr_activation:
                return portfolio.market_area.mfrr_activation_price.get_value(time)
    else:
        return portfolio.market_area.price_forecast_medium.get_forecast(
            parameters.execution_date, time, time
        ).get_value(time)


def get_reserve(
    obj,
    sum_reserves_up: float,
    sum_reserves_down: float,
    sum_automated_reserves_up: float,
    sum_automated_reserves_down: float,
    sum_maximum_power: float,
) -> tuple[float, float, float, float, float]:
    """Calculate reserve values for equipment object."""
    maximum_afrr = obj.maximum_afrr
    maximum_fcr = obj.maximum_fcr

    afrr_up = get_reserve_value("afrr_up")
    afrr_down = get_reserve_value("afrr_down")
    mfrr_up = get_reserve_value("mfrr_up")
    mfrr_down = get_reserve_value("mfrr_down")
    rr_up = get_reserve_value("rr_up")
    rr_down = get_reserve_value("rr_down")
    fcr_up = get_reserve_value("fcr_up")
    fcr_down = get_reserve_value("fcr_down")

    # Calculate reserve totals
    sum_reserves_up += rr_up + mfrr_up
    sum_reserves_down += rr_down + mfrr_down
    sum_automated_reserves_up += min(afrr_up, maximum_afrr) + min(fcr_up, maximum_fcr)
    sum_automated_reserves_down += min(afrr_down, maximum_afrr) + min(fcr_down, maximum_fcr)

    return (
        sum_reserves_up,
        sum_reserves_down,
        sum_automated_reserves_up,
        sum_automated_reserves_down,
        sum_maximum_power,
    )


def get_reserve_value(
    obj: type[Equipment], time: DateTime, reserve_type: str, parameters: PortfolioOptimisationParameters
) -> float:
    """Helper to get reserve value from forecast."""
    reserve_attr = cast(ForecastingMatrix, getattr(obj, f"{reserve_type}_procured"))
    return reserve_attr.get_forecast(parameters.execution_date, time, time).get_value(time)


def get_maximum_power(obj: type[Equipment], time: DateTime, execution_date: DateTime | None = None) -> float:
    if isinstance(obj, Hydro | Storage):
        return obj.maximum_power.get_value(time)
    elif isinstance(obj, Load | Wind | Solar | OtherNonDispatchable):
        return obj.maximum_power_forecast.get_forecast(execution_date, time, time).get_value(time)


def get_minimum_power(obj: type[Equipment], time: DateTime, execution_date: DateTime | None = None) -> float:
    if isinstance(obj, Hydro | Storage):
        if obj.minimum_power:
            return obj.minimum_power.get_value(time)
        else:
            return -get_maximum_power(obj, time)
    elif isinstance(obj, Wind | Solar):
        return (1 - obj.maximum_curtailment_ratio.get_value(time)) * get_maximum_power(obj, time, execution_date)
    elif isinstance(obj, Load):
        return 0


def get_price(obj: type[Equipment], time: DateTime):
    return obj.variable_cost.get_value(time)


def get_maximum_energy(obj: Hydro | Storage, time: DateTime):
    return obj.maximum_energy.get_value(time)


def get_minimum_energy(obj: Hydro | Storage, time: DateTime):
    return obj.minimum_energy.get_value(time)


def get_initial_stock(obj: Storage, parameters: PortfolioOptimisationParameters):
    if (
        len(
            obj.stored_energy.get_forecast(
                parameters.execution_date,
                parameters.init_battery_time.subtract(days=2),
                parameters.init_battery_time,
            )
        )
        == 0
    ):
        obj.initial_stock = get_maximum_energy(
            obj,
            (parameters.start_date - parameters.timestep) * obj.storage_initial_level,
        )
    else:
        obj.initial_stock = (
            obj.stored_energy.get_forecast(
                parameters.execution_date,
                parameters.init_battery_time,
                parameters.init_battery_time,
            )
            .dataframe.select("time")
            .to_series()
            .to_list()[0]
        )


def get_initial_level(obj: Hydro, parameters: PortfolioOptimisationParameters):
    if len(
        (
            obj.stored_energy.get_forecast(
                parameters.execution_date,
                parameters.start_date - parameters.timestep,
                parameters.end_date,
            )
        )
        == 0
    ):
        return obj.initial_level.filter([parameters.start_date - parameters.timestep, parameters.end_date])
    else:
        if (
            obj.stored_energy.get_forecast(
                parameters.execution_date,
                parameters.start_date - parameters.timestep,
                parameters.end_date,
            ).first_date()
            < parameters.start_date
        ):
            return obj.stored_energy.get_forecast(
                parameters.execution_date,
                parameters.start_date - parameters.timestep,
                parameters.end_date,
            )

        else:
            return obj.initial_level.filter([parameters.start_date - parameters.timestep, parameters.end_date])


def get_maximum_automated(obj: type[Equipment]) -> float:
    return obj.maximum_afrr + obj.maximum_fcr
