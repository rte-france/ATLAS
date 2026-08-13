"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pendulum

from atlas.modules.day_ahead_orders.steps.thermal.orders.factory import ThermalCouplingFactory, ThermalOrderFactory

if TYPE_CHECKING:
    from pendulum import DateTime, Duration

    from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
    from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
    from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
    from atlas.modules.day_ahead_orders.steps.thermal.orders.time_frames import ThermalTimeFrames


# Order-name prefixes that may sit as children of an inflexible Pmin order.
_FLEXIBLE_CHILD_TYPES = (
    "flexible_order",
    "manual_upward_reserve_order",
    "automated_upward_reserve_order",
    "manual_downward_reserve_order",
    "automated_downward_reserve_order",
)


def build_inflexible_layer(
    unit: ThermalDAO,
    tf: ThermalTimeFrames,
    flexible_orders: list[OrderDAO],
    ed: DateTime,
    step: Duration,
    case: str,
    has_startup: bool,
    T_start: int,
    T_stop: int,
    q_min: float,
) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
    """
    Build the inflexible layer: startup ramp, shutdown ramp, Pmin orders, couplings,
    and the startup-cost amortization.

    :param flexible_orders: Flex orders already built — used to wire parent-child couplings.
    :param case: Price scenario name ("" for base, "<case>" for intermediate). Also used to
        derive the ``scenario_name`` passed to factories (here equal to ``case``).
    """
    scenario_name = case
    orders: list[OrderDAO] = []
    couplings: list[OrderCouplingDAO] = []

    q_step_up = q_min if T_start == 0 else q_min / T_start
    q_step_down = q_min if T_stop == 0 else q_min / T_stop

    Q = 0.0
    inflexible_orders: list[OrderDAO] = []

    # Startup ramp orders. Skipped when the startup is not visible in the current window
    # (prevents emitting incomplete ramps at the simulation boundary).
    if tf.K_start > 0:
        for t, i in zip(tf.startup, range(tf.K_start + 1), strict=False):
            q_sell = round((T_start - tf.K_start + i) * q_step_up) if tf.startup_ends_here else round(i * q_step_up)
            ramp = ThermalOrderFactory.startup_ramp(unit, q_sell, t, step, ed, scenario_name)
            orders.append(ramp)
            inflexible_orders.append(ramp)
            Q += q_sell

    # Shutdown ramp orders. Same boundary rule as startup.
    if tf.K_stop > 0:
        for t, i in zip(tf.shutdown, range(tf.K_stop + 1), strict=False):
            q_sell = (
                round((T_stop - i) * q_step_down)
                if tf.shutdown_starts_here
                else round(q_min - (T_stop - tf.K_stop + i) * q_step_down)
            )
            ramp = ThermalOrderFactory.shutdown_ramp(unit, q_sell, t, step, ed, scenario_name)
            orders.append(ramp)
            inflexible_orders.append(ramp)
            Q += q_sell

    # Pmin orders + parent-child couplings to existing flexible orders at the same timestep.
    # O(1) flex lookup by reconstructed name suffix.
    flex_by_name: dict[str, OrderDAO] = {bid.name: bid for bid in flexible_orders}
    flex_suffix = f"_with_price_{case}" if case else "_with_price"

    last_t: DateTime | None = None
    for t_raw in tf.inflexible:
        t = pendulum.instance(t_raw)
        last_t = t
        formatted_t = t.format("DD_MM_YYYY_HH_mm_ss")
        min_p = unit.minimum_power.get_value(t)
        variable_cost = unit.variable_cost.get_value(t)
        pmin_order = ThermalOrderFactory.inflexible(unit, min_p, variable_cost, t, step, ed, case)
        orders.append(pmin_order)
        inflexible_orders.append(pmin_order)
        Q += min_p

        flex_name_root = f"_at_{formatted_t}_for_unit_{unit.name}{flex_suffix}"
        for flex_type in _FLEXIBLE_CHILD_TYPES:
            child = flex_by_name.get(flex_type + flex_name_root)
            if child is not None:
                couplings.append(ThermalCouplingFactory.parent_children(pmin_order, child, unit.name, t, scenario_name))

    # Identical-ratio coupling tying all inflexible-layer orders together.
    couplings.append(
        ThermalCouplingFactory.identical_ratio(
            inflexible_orders, unit.name, pendulum.DateTime.instance(tf.inflexible[0]), scenario_name
        )
    )

    # Spread the startup cost across the whole inflexible layer.
    # NOTE: uses unit.variable_cost-time-dependent startup_cost at the LAST inflexible timestep, to match prior behavior.
    assert last_t is not None
    amortized_cost = round(unit.startup_cost.get_value(last_t) / Q, 2)
    for order in inflexible_orders:
        if has_startup and tf.startup_ends_here:
            order.price += amortized_cost
        else:
            order.price -= amortized_cost

    return orders, couplings
