"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements HydraulicOrderFormulator.
"""

from pendulum import DateTime

from atlas.enums import OrderType
from atlas.modules.balancing_market_bsp_orders.input_objects.hydro import BalancingHydro
from atlas.modules.balancing_market_bsp_orders.order_formulators.base import AbstractOrderFormulator
from atlas.modules.balancing_market_bsp_orders.parameters import BSPBalancingOrdersParameters
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling

# TODO : placeholder price until fragment-based pricing (water_value + fragment_prices) is implemented
PLACEHOLDER_PRICE = 0.0


class HydraulicOrderFormulator(AbstractOrderFormulator):
    """Formulates balancing orders for hydraulic equipment.

    Upward orders (Sell): the unit increases its output toward maximum_power.
    Downward orders (Buy): the unit decreases its output toward minimum_power.

    Available power:
        - Upward:   maximum_power - forecasted_power - upward_procured
        - Downward: forecasted_power - minimum_power - downward_procured

    The maximum_gradient constraint, when set, limits the available power based on
    the forecasted power evolution between the studied timestep and its neighbors.

    # TODO : fragment-based pricing (water_value + fragment_prices/fragment_volumes) not yet implemented
    # TODO : daily energy constraint (has_daily_energy_constraint) not yet implemented
    # TODO : PHS transition duration constraint not yet implemented
    """

    def __init__(
        self,
        equipment: BalancingHydro,
        time_index: list[DateTime],
        parameters: BSPBalancingOrdersParameters,
    ) -> None:
        super().__init__(equipment, time_index, parameters)
        self.equipment: BalancingHydro = equipment

    def formulate(self) -> tuple[list[Order], list[OrderCoupling]]:
        """
        Formulate upward and downward orders for the hydraulic equipment.

        :return: Tuple of formulated orders and an empty coupling list
        :rtype: tuple[list[Order], list[OrderCoupling]]
        """
        start = self.parameters.temporal.start_date
        end = self.parameters.temporal.end_date
        execution_date = self.parameters.temporal.execution_date
        timestep_minutes = int(self.parameters.temporal.timestep.total_seconds() // 60)

        forecasted_power = self.equipment.power.get_forecast(execution_date, start, end)
        max_power = self.equipment.maximum_power
        min_power = self.equipment.minimum_power

        upward_procured, downward_procured = self.compute_procured_power(
            execution_date, start, end, self.parameters.product_type
        )

        upward_available = max_power - forecasted_power - upward_procured
        downward_available = forecasted_power - min_power - downward_procured

        orders: list[Order] = []

        for time in self.time_index:
            if not self.is_after_setup_delay(time):
                continue

            next_time = time.add(minutes=timestep_minutes)

            qmax_up = max(0.0, upward_available.get_value(time))
            qmax_down = max(0.0, downward_available.get_value(time))

            if self.equipment.maximum_gradient != 0:
                qmax_up, qmax_down = self._apply_gradient_constraint(forecasted_power, time, qmax_up, qmax_down)

            if qmax_up >= 1.0:
                order = self.build_order(
                    order_type=OrderType.Sell,
                    start=time,
                    end=next_time,
                    price=PLACEHOLDER_PRICE,
                    qmin=0.0,
                    qmax=qmax_up,
                )
                if order is not None:
                    orders.append(order)

            # TODO: Constraint not present in prometheus
            if qmax_down >= 1.0:
                order = self.build_order(
                    order_type=OrderType.Buy,
                    start=time,
                    end=next_time,
                    price=PLACEHOLDER_PRICE,
                    qmin=0.0,
                    qmax=qmax_down,
                )
                if order is not None:
                    orders.append(order)

        return orders, []

    def _apply_gradient_constraint(
        self,
        forecasted_power,
        time: DateTime,
        upward_available: float,
        downward_available: float,
    ) -> tuple[float, float]:
        """
        Apply the maximum_gradient constraint to the available upward and downward power at a given timestep.

        Limits the available power based on the forecasted power evolution between the
        studied timestep and its previous/next neighbor, so that the equipment's power
        trajectory never exceeds maximum_gradient per timestep.

        :param forecasted_power: Forecasted power timeseries over the balancing time frame
        :type forecasted_power: Timeseries
        :param time: The timestep being evaluated
        :type time: DateTime
        :param upward_available: Upward available power before the gradient constraint
        :type upward_available: float
        :param downward_available: Downward available power before the gradient constraint
        :type downward_available: float
        :return: Tuple of (upward_available, downward_available) after the gradient constraint
        :rtype: tuple[float, float]
        """
        timestep = self.parameters.temporal.timestep
        execution_date = self.parameters.temporal.execution_date
        # TODO : 2 multiplication in prometheus
        max_grad = self.equipment.maximum_gradient * (timestep.total_seconds() / 60)

        previous_time = time.subtract(minutes=int(timestep.total_seconds() // 60))
        next_time = time.add(minutes=int(timestep.total_seconds() // 60))

        # TODO : How is the behavior without value ?
        previous_forecasted_power = self.equipment.power.get_forecast(
            execution_date, previous_time, previous_time
        ).get_value(previous_time)
        next_forecasted_power = self.equipment.power.get_forecast(execution_date, next_time, next_time).get_value(
            next_time
        )

        if previous_forecasted_power > 0:
            previous_upward_evolution = max(forecasted_power.get_value(time) - previous_forecasted_power, 0)
            previous_downward_evolution = max(previous_forecasted_power - forecasted_power.get_value(time), 0)
        else:
            previous_upward_evolution = 0.0
            previous_downward_evolution = 0.0

        if next_forecasted_power > 0:
            next_upward_evolution = max(next_forecasted_power - forecasted_power.get_value(time), 0)
            next_downward_evolution = max(forecasted_power.get_value(time) - next_forecasted_power, 0)
        else:
            next_upward_evolution = 0.0
            next_downward_evolution = 0.0

        upward_available = min(
            upward_available,
            max_grad - previous_upward_evolution,
            max_grad - next_downward_evolution,
        )
        downward_available = min(
            downward_available,
            max_grad - previous_downward_evolution,
            max_grad - next_upward_evolution,
        )

        return max(0.0, upward_available), max(0.0, downward_available)
