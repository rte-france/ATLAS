"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.order_factory import ThermalCouplingFactory, ThermalOrderFactory


class ThermalPeakLoadOrders:
    def __init__(self, orders_time: list[DateTime], parameters: DayAheadOrdersParameters):
        """
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        """
        self.orders_time = orders_time
        self.parameters = parameters

    def formulate(self, unit: ThermalDAO) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        Formulate orders for a thermic peak load unit. Such orders are time-independent —
        no coupling exists between orders at different timestamps.

        :param unit: the thermal unit to formulate orders for
        :type unit: ThermalDAO
        :return: orders and order couplings generated for this unit
        :rtype: tuple[list[OrderDAO], list[OrderCouplingDAO]]
        """
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        ed = self.parameters.temporal.execution_date
        step = self.parameters.temporal.timestep
        prop_pen = 1 - self.parameters.proportional_reserves_penalty
        auto_pen = self.parameters.automated_unprocured_reserves_penalty
        manual_pen = self.parameters.manual_unprocured_reserves_penalty

        _default = Timeseries.from_index(
            self.parameters.temporal.start_date, step, self.parameters.temporal.end_date, 0
        )

        def _get_forecast(matrix_a, matrix_b) -> Timeseries:
            if matrix_a and matrix_b:
                return matrix_a.get_forecast(
                    ed, self.parameters.temporal.start_date, self.parameters.temporal.end_date
                ) + matrix_b.get_forecast(ed, self.parameters.temporal.start_date, self.parameters.temporal.end_date)
            return _default

        auto_up = _get_forecast(unit.afrr_up_procured, unit.fcr_up_procured)
        auto_dn = _get_forecast(unit.afrr_down_procured, unit.fcr_down_procured)
        manual_up = _get_forecast(unit.mfrr_up_procured, unit.rr_up_procured)
        manual_dn = _get_forecast(unit.mfrr_down_procured, unit.rr_down_procured)

        for t in self.orders_time:
            minimum_power = unit.minimum_power.get_value(t) if unit.minimum_power is not None else 0
            formatted_t = t.format("DD_MM_YYYY_HH_mm_ss")

            if unit.maximum_power.get_value(t) == 0.0 or unit.maximum_power.get_value(t) < minimum_power:
                cfg.logger.warning(
                    f"MaximumPower is null or lower than MinimumPower for unit {unit.name} at time {str(t)}. "
                    "No order will therefore be created."
                )
                continue

            # Inflexible order
            inflexible_order = None
            if minimum_power > 0:
                Q = minimum_power * (1.0 if unit.minimum_time_on.total_hours() == 0.0 else unit.minimum_time_on)
                price = unit.startup_cost.get_value(t) / Q + unit.variable_cost.get_value(t)
                inflexible_order = ThermalOrderFactory.peak_inflexible(
                    unit, minimum_power, price, t, step, ed, formatted_t
                )
                orders.append(inflexible_order)

            # Flexible order
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
                    f"Negative or null amount of energy in the flexible order to be offered by unit {unit.name} at time {str(t)}. "
                    "The order will therefore not be created."
                )
            else:
                flex = ThermalOrderFactory.flexible(
                    unit, q_max, unit.variable_cost.get_value(t), t, step, ed, formatted_t, ""
                )
                orders.append(flex)
                if inflexible_order is not None:
                    couplings.append(
                        ThermalCouplingFactory.parent_children(inflexible_order, flex, unit.name, formatted_t, "")
                    )

            # Reserve orders
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
                        formatted_t,
                        "",
                    )
                    orders.append(reserve_order)
                    if inflexible_order is not None:
                        couplings.append(
                            ThermalCouplingFactory.parent_children(
                                inflexible_order, reserve_order, unit.name, formatted_t, ""
                            )
                        )

        return orders, couplings
