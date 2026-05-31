"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Top-level per-unit order formulation for base and intermediate strategies. Peak units use
a separate formulation path (:mod:`atlas.modules.day_ahead_orders.steps.thermal.strategies.peak`).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast

import atlas.config as cfg
from atlas.enums import ThermalOrderState
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.steps.thermal.orders.flexible_layer import build_flexible_layer
from atlas.modules.day_ahead_orders.steps.thermal.orders.inflexible_layer import build_inflexible_layer
from atlas.modules.day_ahead_orders.steps.thermal.orders.reserve_forecasts import load_reserve_procurement
from atlas.modules.day_ahead_orders.steps.thermal.orders.time_frames import compute_time_frames

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
    from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
    from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
    from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters


def formulate_unit_orders(
    online_timeframe: Timeseries,
    unit: ThermalDAO,
    orders_time: list[DateTime],
    parameters: DayAheadOrdersParameters,
    case: str = "",
) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
    """
    Build the flexible and (optionally) inflexible layers of orders for a single online sub-window.

    :param online_timeframe: State-encoded sub-window over which the unit is online.
    :param unit: Thermal unit.
    :param orders_time: Full reference list of order timesteps.
    :param parameters: Module parameters.
    :param case: Price scenario name ("" for base, scenario label for intermediate).
    :return: Orders and order couplings.
    """
    orders: list[OrderDAO] = []
    couplings: list[OrderCouplingDAO] = []

    online_values = online_timeframe.values
    if ThermalOrderState.OFF in online_values:
        cfg.logger.debug(f"Unit {unit.name} is offline. No orders have been formulated for this unit")
        return orders, couplings

    start = parameters.temporal.start_date
    end = parameters.temporal.end_date
    step = parameters.temporal.timestep
    ed = parameters.temporal.execution_date

    procurement = load_reserve_procurement(unit, ed, start, end, step)

    T_start = int(math.floor(unit.startup_duration / step))
    T_stop = int(math.floor(unit.shutdown_duration / step))
    q_min = unit.minimum_power.max()

    if isinstance(unit.minimum_power, LazyTimeseries):
        min_power = unit.minimum_power.collect()
    else:
        min_power = cast(Timeseries, unit.minimum_power)
    null_minimum_power = min_power.filter(orders_time, inplace=False).min() == 0

    has_startup = ThermalOrderState.STARTUP in online_values

    tf = compute_time_frames(online_timeframe, orders_time, step)

    flexible_orders = build_flexible_layer(unit, tf.flexible, procurement, parameters, ed, step, case)
    orders.extend(flexible_orders)

    if not null_minimum_power:
        inflex_orders, inflex_couplings = build_inflexible_layer(
            unit, tf, flexible_orders, ed, step, case, has_startup, T_start, T_stop, q_min
        )
        orders.extend(inflex_orders)
        couplings.extend(inflex_couplings)

    return orders, couplings
