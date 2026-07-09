"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements LoadOrderFormulator.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import OrderType
from atlas.modules.balancing_market_bsp_orders.input_objects.load import BalancingLoad
from atlas.modules.balancing_market_bsp_orders.order_formulators.base import AbstractOrderFormulator
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


class LoadOrderFormulator(AbstractOrderFormulator):
    """Formulates balancing orders for load equipment.

    Upward orders (Sell): the load reduces its consumption, freeing power upward.
    Downward orders (Buy): the load increases its consumption.

    Available power:
    - Upward:   max_power_forecast - forecasted_power - upward_procured
    - Downward: forecasted_power - downward_procured
    """

    def __init__(
        self,
        equipment: BalancingLoad,
        time_index: list[DateTime],
        parameters: BSPBalancingOrdersParameters,
    ) -> None:
        super().__init__(equipment, time_index, parameters)
        self.equipment: BalancingLoad = equipment

    def formulate(self) -> tuple[list[Order], list[OrderCoupling]]:
        """
        Formulate upward and downward orders for the load equipment.

        :return: Tuple of formulated orders and an empty coupling list
        :rtype: tuple[list[Order], list[OrderCoupling]]
        """
        start = self.parameters.temporal.start_date
        end = self.parameters.temporal.end_date - self.parameters.temporal.timestep

        # Extract the timeseries containing the forecasted power from the Power ForecastMatrix.
        forecasted_power = self.equipment.power.get_forecast(self.parameters.temporal.execution_date, start, end)
        max_power = self.equipment.maximum_power_forecast.get_forecast(
            self.parameters.temporal.execution_date, start, end
        )
        upward_procured, downward_procured = self.compute_procured_power(
            self.parameters.temporal.execution_date, start, end, self.parameters.product_type
        )

        upward_available = -forecasted_power - upward_procured
        downward_available = forecasted_power - max_power - downward_procured

        orders: list[Order] = []

        for time in self.time_index:
            if not self.is_after_setup_delay(time):  # TODO : setup_delay is not only for going from 0 to x ?
                continue

            next_time = time.add(minutes=int(self.parameters.temporal.timestep.total_seconds() // 60))

            # Upward order
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

            # Downward order
            qmax_down = downward_available.get_value(time)
            if qmax_down >= 1.0:
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
