"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.orders.factory import ThermalCouplingFactory, ThermalOrderFactory
from atlas.modules.day_ahead_orders.steps.thermal.orders.reserve_forecasts import load_paired_forecasts_or_zero


class ThermalPeakLoadOrders:
    """
    Order formulation for peak thermal units. Peak orders are time-independent — there is
    no coupling between orders at different timestamps and no LP is involved.
    """

    def __init__(self, orders_time: list[DateTime], parameters: DayAheadOrdersParameters):
        self.orders_time = orders_time
        self.parameters = parameters

    def formulate(self, unit: ThermalDAO) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        Formulate orders for a thermic peak load unit.

        :param unit: the thermal unit to formulate orders for
        :return: orders and order couplings generated for this unit
        """
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        ed = self.parameters.temporal.execution_date
        step = self.parameters.temporal.timestep
        start = self.parameters.temporal.start_date
        end = self.parameters.temporal.end_date
        prop_pen = 1 - self.parameters.proportional_reserves_penalty
        auto_pen = self.parameters.automated_unprocured_reserves_penalty
        manual_pen = self.parameters.manual_unprocured_reserves_penalty

        auto_up = load_paired_forecasts_or_zero(unit.afrr_up_procured, unit.fcr_up_procured, ed, start, end, step)
        auto_dn = load_paired_forecasts_or_zero(unit.afrr_down_procured, unit.fcr_down_procured, ed, start, end, step)
        manual_up = load_paired_forecasts_or_zero(unit.mfrr_up_procured, unit.rr_up_procured, ed, start, end, step)
        manual_dn = load_paired_forecasts_or_zero(unit.mfrr_down_procured, unit.rr_down_procured, ed, start, end, step)

        for t in self.orders_time:
            minimum_power = unit.minimum_power.get_value(t) if unit.minimum_power is not None else 0

            if unit.maximum_power.get_value(t) == 0.0 or unit.maximum_power.get_value(t) < minimum_power:
                cfg.logger.warning(
                    f"MaximumPower is null or lower than MinimumPower for unit {unit.name} at time {str(t)}. "
                    "No order will therefore be created."
                )
                continue

            inflexible_order = None
            if minimum_power > 0:
                Q = minimum_power * (1.0 if unit.minimum_time_on.total_hours() == 0.0 else unit.minimum_time_on)
                price = unit.startup_cost.get_value(t) / Q + unit.variable_cost.get_value(t)
                inflexible_order = ThermalOrderFactory.peak_inflexible(unit, minimum_power, price, t, step, ed)
                orders.append(inflexible_order)

            q_max = (
                unit.maximum_power.get_value(t)
                - minimum_power
                - manual_dn.get_value(t)
                - manual_up.get_value(t)
                - auto_dn.get_value(t)
                - auto_up.get_value(t)
            )
            if q_max <= 0.0:
                cfg.logger.warning(
                    f"Negative or null amount of energy in the flexible order to be offered by unit {unit.name} "
                    f"at time {str(t)}. The order will therefore not be created."
                )
            else:
                flex = ThermalOrderFactory.flexible(unit, q_max, unit.variable_cost.get_value(t), t, step, ed)
                orders.append(flex)
                if inflexible_order is not None:
                    couplings.append(ThermalCouplingFactory.parent_children(inflexible_order, flex, unit.name, t))

            for qty, direction, reserve_type, penalty in (
                (auto_dn.get_value(t), "downward", "automated", auto_pen),
                (manual_dn.get_value(t), "downward", "manual", manual_pen),
                (auto_up.get_value(t), "upward", "automated", auto_pen),
                (manual_up.get_value(t), "upward", "manual", manual_pen),
            ):
                if qty > 0.0:
                    reserve_order = ThermalOrderFactory.reserve(
                        unit,
                        qty,
                        unit.variable_cost.get_value(t),
                        penalty,
                        direction,
                        reserve_type,
                        prop_pen,
                        t,
                        step,
                        ed,
                    )
                    orders.append(reserve_order)
                    if inflexible_order is not None:
                        couplings.append(
                            ThermalCouplingFactory.parent_children(inflexible_order, reserve_order, unit.name, t)
                        )

        return orders, couplings
