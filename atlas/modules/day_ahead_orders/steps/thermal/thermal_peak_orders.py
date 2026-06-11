"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.core.math.timeseries import Timeseries
from atlas.enums import CouplingType, OrderType, Product
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.objects.equipment.equipment import Equipment


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
        This function formulates orders for a thermic peak load unit. Such orders
        have the particularity of being time-independent, so there is no link between
        two orders that are submitted on different timestamps.

        :param unit: the thermal unit to formulate orders for
        :type unit: Equipment
        :return: orders and order couplings generated for this unit
        :rtype: tuple[list[OrderDAO], list[OrderCouplingDAO]]
        """
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        # Get the reserve procurements at the executionDate and collapse them into automated and manual reserves procurements
        automated_reserves_up_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            0,
        )
        automated_reserves_down_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            0,
        )
        manual_reserves_up_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            0,
        )
        manual_reserves_down_procured = Timeseries.from_index(
            self.parameters.temporal.start_date,
            self.parameters.temporal.timestep,
            self.parameters.temporal.end_date,
            0,
        )

        if unit.afrr_up_procured and unit.fcr_up_procured:
            automated_reserves_up_procured = unit.afrr_up_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date,
            ) + unit.fcr_up_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date,
            )
        if unit.afrr_down_procured and unit.fcr_down_procured:
            automated_reserves_down_procured = unit.afrr_down_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date,
            ) + unit.fcr_down_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date,
            )
        if unit.mfrr_up_procured and unit.rr_up_procured:
            manual_reserves_up_procured = unit.mfrr_up_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date,
            ) + unit.rr_up_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date,
            )
        if unit.mfrr_down_procured and unit.rr_down_procured:
            manual_reserves_down_procured = unit.mfrr_down_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date,
            ) + unit.rr_down_procured.get_forecast(
                self.parameters.temporal.execution_date,
                self.parameters.temporal.start_date,
                self.parameters.temporal.end_date,
            )

        for t in self.orders_time:
            # Reads the minimum power and decides whether an inflexible order should be generated or not
            minimum_power = unit.minimum_power.get_value(t) if unit.minimum_power is not None else 0
            generate_inflexible_order = minimum_power > 0

            # MaximumPower is used to store planned or forced outages (value at 0), in which cases it might be lower than MinimumPower
            if unit.maximum_power.get_value(t) == 0.0 or unit.maximum_power.get_value(t) < minimum_power:
                cfg.logger.warning(
                    f"MaximumPower is null or lower than MinimumPower for unit {unit.name} at time {str(t)}. "
                    "No order will therefore be created."
                )
                continue

            # Inflexible order
            # ================

            inflexible_order = None
            if generate_inflexible_order:
                # Compute the price
                Q = minimum_power * (1.0 if unit.minimum_time_on.total_hours() == 0.0 else unit.minimum_time_on)
                price = unit.startup_cost.get_value(t) / Q + unit.variable_cost.get_value(t)

                # Create the instance
                inflexible_order = OrderDAO(
                    name=f"inflexible_order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}",
                    market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=minimum_power,
                    qmin=minimum_power,
                    price=price,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=self.parameters.temporal.execution_date,
                    start_date=t,  # type: ignore [arg-type]
                    end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                )
                orders.append(inflexible_order)

            # Flexible order
            # ==============

            # Compute the maximum power of the flexible order
            q_max = (
                unit.maximum_power.get_value(t)
                - minimum_power
                - manual_reserves_down_procured.get_value(t)
                - manual_reserves_up_procured.get_value(t)
                - automated_reserves_down_procured.get_value(t)
                - automated_reserves_up_procured.get_value(t)
            )

            # We only formulate the order if its maximal power is positive
            if q_max <= 0.0:
                cfg.logger.warning(
                    f"Negative or null amount of energy in the flexible order to be offered by unit {unit.name} at time {str(t)}. "
                    "The order will therefore not be created."
                )
            else:
                # Flexible order
                order, coupling = self.create_order_and_link(
                    inflexible_order=inflexible_order,
                    t=t,
                    unit=unit,
                    order_name=f"flexible_order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}",
                    q_max=q_max,
                    q_min=0,
                    price=unit.variable_cost.get_value(t),
                    link_name=f"parent_children_inflexible_flexible_orders_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}",
                )
                orders.append(order)
                if coupling is not None:
                    couplings.append(coupling)

            # Reserve orders
            # ==============

            # Automated downward reserves requirements
            if automated_reserves_down_procured.get_value(t) > 0.0:
                order, coupling = self.create_order_and_link(
                    inflexible_order=inflexible_order,
                    t=t,
                    unit=unit,
                    order_name=f"automated_downward_reserve_order_at_{t}_for_unit_{unit.name}",
                    q_max=automated_reserves_down_procured.get_value(t),
                    q_min=(1 - self.parameters.proportional_reserves_penalty)
                    * automated_reserves_down_procured.get_value(t),
                    price=unit.variable_cost.get_value(t) - self.parameters.automated_unprocured_reserves_penalty,
                    link_name=f"parent_children_automated_downward_reserve_inflexible_orders_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}",
                )
                orders.append(order)
                if coupling is not None:
                    couplings.append(coupling)

            # Manual downward reserves requirements
            if manual_reserves_down_procured.get_value(t) > 0.0:
                order, coupling = self.create_order_and_link(
                    inflexible_order=inflexible_order,
                    t=t,
                    unit=unit,
                    order_name=f"manual_downward_reserve_order_at_{t}_for_unit_{unit.name}",
                    q_max=manual_reserves_down_procured.get_value(t),
                    q_min=(1 - self.parameters.proportional_reserves_penalty)
                    * manual_reserves_down_procured.get_value(t),
                    price=unit.variable_cost.get_value(t) - self.parameters.manual_unprocured_reserves_penalty,
                    link_name=f"parent_children_manual_downward_reserve_inflexible_orders_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}",
                )
                orders.append(order)
                if coupling is not None:
                    couplings.append(coupling)

            # Automated upward reserves requirements
            if automated_reserves_up_procured.get_value(t) > 0.0:
                order, coupling = self.create_order_and_link(
                    inflexible_order=inflexible_order,
                    t=t,
                    unit=unit,
                    order_name=f"automated_upward_reserve_order_at_{t}_for_unit_{unit.name}",
                    q_max=automated_reserves_up_procured.get_value(t),
                    q_min=(1 - self.parameters.proportional_reserves_penalty)
                    * automated_reserves_up_procured.get_value(t),
                    price=(unit.variable_cost.get_value(t) + self.parameters.automated_unprocured_reserves_penalty),
                    link_name=f"parent_children_automated_upward_reserve_inflexible_orders_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}",
                )
                orders.append(order)
                if coupling is not None:
                    couplings.append(coupling)

            # Manual upward reserves requirements
            if manual_reserves_up_procured.get_value(t) > 0.0:
                order, coupling = self.create_order_and_link(
                    inflexible_order=inflexible_order,
                    t=t,
                    unit=unit,
                    order_name=f"manual_upward_reserve_order_at_{t}_for_unit_{unit.name}",
                    q_max=manual_reserves_up_procured.get_value(t),
                    q_min=(1 - self.parameters.proportional_reserves_penalty)
                    * manual_reserves_up_procured.get_value(t),
                    price=unit.variable_cost.get_value(t) + self.parameters.manual_unprocured_reserves_penalty,
                    link_name=f"parent_children_manual_upward_reserve_inflexible_orders_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}",
                )
                orders.append(order)
                if coupling is not None:
                    couplings.append(coupling)

        return orders, couplings

    def create_order_and_link(
        self,
        inflexible_order: OrderDAO | None,
        t: DateTime,
        unit: Equipment,
        order_name: str,
        q_max: float,
        q_min: float,
        price: float,
        link_name: str,
    ) -> tuple[OrderDAO, OrderCouplingDAO | None]:
        """
        :param inflexible_order: a InflexibleOrder instance
        :type inflexible_order: InflexibleOrder
        :param t: the current time
        :type t: DateTime
        :param unit: the unit
        :type unit: Equipment
        :param order_name: the name of the order
        :type order_name: str
        :param q_max: the maximum power
        :type q_max: float
        :param q_min: the minimum power
        :type q_min: float
        :param price: the price
        :type price: float
        :param link_name: the link name
        :type link_name: str
        :return: the created order and its optional parent-children coupling
        :rtype: tuple[OrderDAO, OrderCouplingDAO | None]
        """
        order = OrderDAO(
            name=order_name,
            market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
            portfolio=unit.portfolio,
            equipment=unit,
            qmax=q_max,
            qmin=q_min,
            price=price,
            product=Product.DayAhead,
            order_type=OrderType.Sell,
            is_agent_tso=False,
            execution_date=self.parameters.temporal.execution_date,
            start_date=t,  # type: ignore [arg-type]
            end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
        )
        coupling = None
        if inflexible_order is not None:
            coupling = OrderCouplingDAO(
                name=link_name,
                coupling_type=CouplingType.PARENT_CHILDREN,
                orders=[inflexible_order, order],
            )
        return order, coupling
