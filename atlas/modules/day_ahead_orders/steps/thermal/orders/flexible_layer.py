"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import atlas.config as cfg
from atlas.modules.day_ahead_orders.steps.thermal.orders.factory import ThermalOrderFactory

if TYPE_CHECKING:
    from pendulum import DateTime, Duration

    from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
    from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
    from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
    from atlas.modules.day_ahead_orders.steps.thermal.orders.reserve_forecasts import ReserveProcurement


def build_flexible_layer(
    unit: ThermalDAO,
    flexible_timesteps: list[DateTime],
    procurement: ReserveProcurement,
    parameters: DayAheadOrdersParameters,
    ed: DateTime,
    step: Duration,
    scenario_name: str,
) -> list[OrderDAO]:
    """
    Build flexible-layer orders for a thermal unit over the stable-ON time frame.

    Emits at most one flexible energy order per timestep, plus up to four reserve orders
    (automated/manual × up/down) when procurement is strictly positive.

    The flexible order quantity is ``Pmax - Pmin - sum(reserves procured)`` at each
    timestep. When this is non-positive at a given step, the flexible order at that step
    is skipped with a warning, but reserve orders are still emitted.
    """
    orders: list[OrderDAO] = []
    if not flexible_timesteps:
        return orders

    prop_pen = 1 - parameters.proportional_reserves_penalty
    auto_pen = parameters.automated_unprocured_reserves_penalty
    manual_pen = parameters.manual_unprocured_reserves_penalty

    q_max_ts = (
        unit.maximum_power.filter(flexible_timesteps, inplace=False)
        - unit.minimum_power.filter(flexible_timesteps, inplace=False)
        - procurement.manual_down.filter(flexible_timesteps, inplace=False)
        - procurement.manual_up.filter(flexible_timesteps, inplace=False)
        - procurement.automated_down.filter(flexible_timesteps, inplace=False)
        - procurement.automated_up.filter(flexible_timesteps, inplace=False)
    )

    flex_qmax = q_max_ts.values
    flex_vc = unit.variable_cost.filter(flexible_timesteps, inplace=False).values
    flex_auto_dn = procurement.automated_down.filter(flexible_timesteps, inplace=False).values
    flex_man_dn = procurement.manual_down.filter(flexible_timesteps, inplace=False).values
    flex_auto_up = procurement.automated_up.filter(flexible_timesteps, inplace=False).values
    flex_man_up = procurement.manual_up.filter(flexible_timesteps, inplace=False).values

    for t, q_max, variable_cost, auto_dn, man_dn, auto_up, man_up in zip(
        flexible_timesteps, flex_qmax, flex_vc, flex_auto_dn, flex_man_dn, flex_auto_up, flex_man_up, strict=True
    ):
        if q_max <= 0.0:
            cfg.logger.warning(
                f"Negative or null amount of energy in the flexible order to be offered by unit {unit.name} at time {str(t)}. "
                "The order will therefore not be created."
            )
        else:
            orders.append(ThermalOrderFactory.flexible(unit, q_max, variable_cost, t, step, ed, scenario_name))

        # Reserve requirement orders. Each direction × class is independent and only emitted when procured > 0.
        for qty, direction, reserve_type, penalty in (
            (auto_dn, "downward", "automated", auto_pen),
            (man_dn, "downward", "manual", manual_pen),
            (auto_up, "upward", "automated", auto_pen),
            (man_up, "upward", "manual", manual_pen),
        ):
            if qty > 0.0:
                orders.append(
                    ThermalOrderFactory.reserve(
                        unit,
                        qty,
                        variable_cost,
                        penalty,
                        direction,
                        reserve_type,
                        prop_pen,
                        t,
                        step,
                        ed,
                        scenario_name,
                    )
                )

    return orders
