"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements WindPvOrderFormulator.
"""

from atlas.enums import OrderType
from atlas.modules.balancing_market_bsp_orders.order_formulators.base import AbstractOrderFormulator
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


class WindPvOrderFormulator(AbstractOrderFormulator):
    """Formulates balancing orders for wind and solar equipment.

    Upward orders (Sell): only formulated when res_self_balancing is True.
        The unit increases its output toward maximum_power_forecast.

    Downward orders (Buy): two types may be formulated per timestep:
        - Self-balancing order: formulated when res_self_balancing is True and
          forecasted_power exceeds maximum_power_forecast. Priced at market_price_cap
          to ensure acceptance at all costs.
        - Regular order: formulated on the remaining downward available power after
          subtracting the self-balancing quantity.

    Available power:
        - Upward:   maximum_power_forecast - forecasted_power - upward_procured
        - Downward: forecasted_power - min_power - downward_procured
          where min_power = maximum_power_forecast * (1 - maximum_curtailment_ratio)
    """

    def formulate(self) -> tuple[list[Order], list[OrderCoupling]]:
        """
        Formulate upward and downward orders for the wind or solar equipment.

        :return: Tuple of formulated orders and an empty coupling list
        :rtype: tuple[list[Order], list[OrderCoupling]]
        """
        start = self.parameters.temporal.start_date
        end = self.parameters.temporal.end_date
        execution_date = self.parameters.temporal.execution_date
        timestep_minutes = int(self.parameters.temporal.timestep.total_seconds() // 60)

        forecasted_power = self.equipment.power.get_forecast(execution_date, start, end)
        max_power = self.equipment.maximum_power_forecast.get_forecast(execution_date, start, end)

        upward_procured, downward_procured = self.compute_procured_power(
            execution_date, start, end, self.parameters.product_type
        )

        upward_available = max_power - forecasted_power - upward_procured

        # Minimum power = maximum_power_forecast * (1 - maximum_curtailment_ratio)
        min_power = max_power * (1 - self.equipment.maximum_curtailment_ratio)
        downward_available = forecasted_power - min_power - downward_procured

        orders: list[Order] = []

        for time in self.time_index:
            if not self.is_after_setup_delay(time):
                continue

            next_time = time.add(minutes=timestep_minutes)

            # --- Upward order (only with self-balancing strategy)
            qmax_up = max(0.0, upward_available.get_value(time))
            if qmax_up > 0 and self.parameters.res_self_balancing:
                order = self.build_order(
                    order_type=OrderType.Sell,
                    start=time,
                    end=next_time,
                    price=self.equipment.variable_cost.get_value(time),
                    qmin=0.0,
                    qmax=qmax_up,
                )
                if order is not None:
                    order.name += "_selfbal"
                    orders.append(order)

            # --- Downward orders
            qmax_down = downward_available.get_value(time)
            if qmax_down < 1.0:
                continue

            # Self-balancing downward order: covers the excess of forecasted power over max power
            self_balancing_qmax = max(0.0, round(forecasted_power.get_value(time) - max_power.get_value(time)))
            if self.parameters.res_self_balancing and self_balancing_qmax >= 1.0:
                order = self.build_order(
                    order_type=OrderType.Buy,
                    start=time,
                    end=next_time,
                    price=float(self.parameters.market_price_cap),
                    qmin=0.0,
                    qmax=self_balancing_qmax,
                )
                if order is not None:
                    order.name += "_selfbal"
                    orders.append(order)
            else:
                self_balancing_qmax = 0.0

            # Regular downward order: remaining available power after self-balancing
            regular_qmax = max(0.0, round(qmax_down - self_balancing_qmax))
            if regular_qmax == 0:
                continue

            order = self.build_order(
                order_type=OrderType.Buy,
                start=time,
                end=next_time,
                price=self.equipment.variable_cost.get_value(time),
                qmin=0.0,
                qmax=regular_qmax,
            )
            if order is not None:
                orders.append(order)

        return orders, []
