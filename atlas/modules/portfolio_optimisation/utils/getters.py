from datetime import datetime
from typing import cast

from pendulum import DateTime

from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.models.equipment.equipment import Equipment
from atlas.modules.portfolio_optimisation.models.hydro import HydroPO
from atlas.modules.portfolio_optimisation.models.load import LoadPO
from atlas.modules.portfolio_optimisation.models.other_non_dispatchable import OtherNonDispatchablePO
from atlas.modules.portfolio_optimisation.models.solar import SolarPO
from atlas.modules.portfolio_optimisation.models.storage import StoragePO
from atlas.modules.portfolio_optimisation.models.thermal import ThermalPO
from atlas.modules.portfolio_optimisation.models.wind import WindPO
from atlas.modules.portfolio_optimisation.parameters import MarketEnum, PortfolioOptimisationParameters


def get_reserve(
    obj: Equipment,
    sum_reserves_up: float,
    sum_reserves_down: float,
    sum_automated_reserves_up: float,
    sum_automated_reserves_down: float,
    sum_maximum_power: float,
    time: DateTime,
    parameters: PortfolioOptimisationParameters,
) -> tuple[float, float, float, float, float]:
    """Calculate reserve values for equipment object."""
    maximum_afrr = obj.maximum_afrr
    maximum_fcr = obj.maximum_fcr

    afrr_up = get_reserve_value(obj, time, "afrr_up", parameters)
    afrr_down = get_reserve_value(obj, time, "afrr_down", parameters)
    mfrr_up = get_reserve_value(obj, time, "mfrr_up", parameters)
    mfrr_down = get_reserve_value(obj, time, "mfrr_down", parameters)
    rr_up = get_reserve_value(obj, time, "rr_up", parameters)
    rr_down = get_reserve_value(obj, time, "rr_down", parameters)
    fcr_up = get_reserve_value(obj, time, "fcr_up", parameters)
    fcr_down = get_reserve_value(obj, time, "fcr_down", parameters)

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
    obj: Equipment, time: DateTime, reserve_type: str, parameters: PortfolioOptimisationParameters
) -> float:
    """Helper to get reserve value from forecast."""
    reserve_attr = cast(ForecastingMatrix, getattr(obj, f"{reserve_type}_procured"))
    return reserve_attr.get_forecast(parameters.execution_date, time, time).get_value(time)


def get_maximum_power(obj: Equipment, time: DateTime, execution_date: datetime | DateTime | str | None = None) -> float:
    if isinstance(obj, HydroPO | StoragePO | ThermalPO):
        return obj.maximum_power.get_value(time)
    elif isinstance(obj, LoadPO | WindPO | SolarPO | OtherNonDispatchablePO):
        if execution_date:
            return obj.maximum_power_forecast.get_forecast(execution_date, time, time).get_value(time)
        else:
            raise RuntimeError(
                "Missing execution date argument for a Load, Wind, Solar or OtherNonDispatchable equipment"
            )
    else:
        raise RuntimeError("Unrecognized Equipment type")


def get_minimum_power(obj: Equipment, time: DateTime, execution_date: DateTime | None = None) -> float | None:
    if isinstance(obj, HydroPO | StoragePO | ThermalPO):
        if obj.minimum_power:
            return obj.minimum_power.get_value(time)
        else:
            return -get_maximum_power(obj, time)
    elif isinstance(obj, WindPO | SolarPO):
        return (1 - obj.maximum_curtailment_ratio.get_value(time)) * get_maximum_power(obj, time, execution_date)
    elif isinstance(obj, LoadPO):
        return 0
    else:
        RuntimeError("Unrecognized Equipment type")


def get_variable_cost(obj: Equipment, time: DateTime):
    return obj.variable_cost.get_value(time)


def get_maximum_energy(obj: StoragePO, time: DateTime):
    return obj.maximum_energy.get_value(time)


def get_maximum_automated(obj: Equipment) -> float:
    return obj.maximum_afrr + obj.maximum_fcr


def get_upstream_energy(
    obj: Equipment,
    time: DateTime,
    parameters: PortfolioOptimisationParameters,
) -> float:
    """Get upstream energy (bought or sold) based on market type."""
    if parameters.market == MarketEnum.rr_activation:
        return obj.rr_activated.get_value(time)
    elif parameters.market == MarketEnum.mfrr_activation:
        return obj.mfrr_activated.get_value(time)
    else:
        return obj.total_id_cleared_quantity.get_value(time) + obj.da_cleared_quantity.get_value(time)
