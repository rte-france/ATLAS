"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, cast

from pendulum import DateTime

from atlas.enum import MarketType
from atlas.math.forecasting_matrix import ForecastingMatrix
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters

if TYPE_CHECKING:
    from atlas.modules.portfolio_optimisation.models import EquipmentPO


def get_reserve(
    obj: EquipmentPO,
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
    sum_automated_reserves_up += min(afrr_up, maximum_afrr or 0) + min(fcr_up, maximum_fcr or 0)
    sum_automated_reserves_down += min(afrr_down, maximum_afrr or 0) + min(fcr_down, maximum_fcr or 0)

    return (
        sum_reserves_up,
        sum_reserves_down,
        sum_automated_reserves_up,
        sum_automated_reserves_down,
        sum_maximum_power,
    )


def get_reserve_value(
    obj: EquipmentPO, time: DateTime, reserve_type: str, parameters: PortfolioOptimisationParameters
) -> float:
    """Helper to get reserve value from forecast."""
    reserve_attr = cast(ForecastingMatrix, getattr(obj, f"{reserve_type}_procured"))
    return reserve_attr.get_forecast(parameters.execution_date, time, time).get_value(time)


def get_maximum_power(
    obj: EquipmentPO, time: DateTime, execution_date: datetime | DateTime | str | None = None
) -> float:
    obj_type = type(obj).__name__

    if obj_type in ("HydroPO", "StoragePO", "ThermalPO"):
        return obj.maximum_power.get_value(time)  # type: ignore[union-attr]
    elif obj_type in ("LoadPO", "WindPO", "SolarPO", "OtherNonDispatchablePO"):
        if execution_date:
            return obj.maximum_power_forecast.get_forecast(execution_date, time, time).get_value(time)  # type: ignore[union-attr]
        else:
            raise RuntimeError(
                "Missing execution date argument for a Load, Wind, Solar or OtherNonDispatchable equipment"
            )
    else:
        raise RuntimeError("Unrecognized Equipment type")


def get_variable_cost(obj: EquipmentPO, time: DateTime):
    if obj.variable_cost is not None:
        return obj.variable_cost.get_value(time)
    return 0.0


def get_maximum_automated(obj: EquipmentPO) -> float:
    return (obj.maximum_afrr or 0.0) + (obj.maximum_fcr or 0.0)


def get_upstream_energy(
    obj: EquipmentPO,
    time: DateTime,
    parameters: PortfolioOptimisationParameters,
) -> float:
    """Get upstream energy (bought or sold) based on market type."""
    if parameters.market == MarketType.rr_activation:
        if obj.rr_activated is not None:
            return obj.rr_activated.get_value(time)
        return 0.0
    elif parameters.market == MarketType.mfrr_activation:
        if obj.mfrr_activated is not None:
            return obj.mfrr_activated.get_value(time)
        return 0.0
    else:
        total_id = obj.total_id_cleared_quantity.get_value(time) if obj.total_id_cleared_quantity is not None else 0.0
        da_cleared = obj.da_cleared_quantity.get_value(time) if obj.da_cleared_quantity is not None else 0.0
        return total_id + da_cleared
