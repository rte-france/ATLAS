"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ThermalOrderFormulator.
"""

import atlas.config as cfg
from atlas.enums import OrderType
from atlas.modules.balancing_market_bsp_orders.order_formulators.base import AbstractOrderFormulator
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


class ThermalOrderFormulator(AbstractOrderFormulator):
    """Formulates balancing orders for thermal equipment.

    Upward orders (Sell):   maximum_power - forecasted_power
    Downward orders (Buy):  forecasted_power - minimum_power
    """

    def formulate(self) -> tuple[list[Order], list[OrderCoupling]]:
        """
        Formulate upward and downward orders for the thermal equipment.

        :return: Tuple of formulated orders and an empty coupling list
        :rtype: tuple[list[Order], list[OrderCoupling]]
        """
        start = self.parameters.temporal.start_date
        end = self.parameters.temporal.end_date - self.parameters.temporal.timestep
        execution_date = self.parameters.temporal.execution_date
        timestep_minutes = int(self.parameters.temporal.timestep.total_seconds() // 60)

        forecasted_power = self.equipment.power.get_forecast(execution_date, start, end)
        max_power = self.equipment.maximum_power.slice(start, end)
        min_power = self.equipment.minimum_power.slice(start, end)

        upward_available = max_power - forecasted_power
        downward_available = forecasted_power - min_power

        orders: list[Order] = []

        for time in self.target_times:
            if not self.is_after_setup_delay(time):
                continue

            power_at_time = forecasted_power.get_value(time)
            if 0 < power_at_time < min_power.get_value(time):
                upward_available.set_value(time, 0.0)
                downward_available.set_value(time, 0.0)

            next_time = time.add(minutes=timestep_minutes)

            qmax_up = max(0.0, upward_available.get_value(time))
            if qmax_up > 0:
                order = self.build_order(
                    order_type=OrderType.Sell,
                    start=time,
                    end=next_time,
                    price=self.equipment.variable_cost.get_value(time),
                    qmin=0.0,
                    qmax=qmax_up,
                )
                if order is not None:
                    orders.append(order)

            qmax_down = downward_available.get_value(time)
            if qmax_down < 1.0:
                continue

            order = self.build_order(
                order_type=OrderType.Buy,
                start=time,
                end=next_time,
                price=self.equipment.variable_cost.get_value(time),
                qmin=0.0,
                qmax=qmax_down,
            )
            if order is not None:
                orders.append(order)

        cfg.logger.info(f"Formulation of orders on equipment {self.equipment.name} completed")
        return orders, []
