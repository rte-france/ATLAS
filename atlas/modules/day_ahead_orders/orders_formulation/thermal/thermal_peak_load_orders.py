"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas import Equipment, Order, OrderCoupling, Timeseries
from atlas.enum import CouplingType, OrderType, Product, ThermalStrategy
from atlas.modules.day_ahead_orders.dao_output_dataset import DayAheadOrdersOutputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters


class ThermalPeakLoadOrders:
    def __init__(
        self, dataset: DayAheadOrdersOutputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ):
        self.dataset = dataset
        self.orders_time = orders_time
        self.parameters = parameters

    def formulate_thermal_peak_load_orders(self) -> None:
        """
        This function formulates orders for the thermic peak load units. Such orders
        have the particularity of being time-independent, so there is no link between
        two orders that are submitted on different timestamps.
        Peak load units are identified from an attribute of the thermic class.

        Returns None
        """

        # Filter the peak load instances
        equipments_list = [eqt for eqt in self.dataset.thermal if eqt.strategy == ThermalStrategy.PEAK]

        for unit in equipments_list:
            # Get the reserve procurements at the executionDate and collapse them into automated and manual reserves procurements
            automated_reserves_up_procured = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
            )
            automated_reserves_down_procured = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
            )
            manual_reserves_up_procured = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
            )
            manual_reserves_down_procured = Timeseries.from_index(
                self.parameters.start_date, self.parameters.time_step, self.parameters.end_date, 0
            )

            if unit.afrr_up_procured and unit.fcr_up_procured:
                automated_reserves_up_procured = unit.afrr_up_procured.get_forecast(
                    self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
                ) + unit.fcr_up_procured.get_forecast(
                    self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
                )
            if unit.afrr_down_procured and unit.fcr_down_procured:
                automated_reserves_down_procured = unit.afrr_down_procured.get_forecast(
                    self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
                ) + unit.fcr_down_procured.get_forecast(
                    self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
                )
            if unit.mfrr_up_procured and unit.rr_up_procured:
                manual_reserves_up_procured = unit.mfrr_up_procured.get_forecast(
                    self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
                ) + unit.rr_up_procured.get_forecast(
                    self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
                )
            if unit.mfrr_down_procured and unit.rr_down_procured:
                manual_reserves_down_procured = unit.mfrr_down_procured.get_forecast(
                    self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
                ) + unit.rr_down_procured.get_forecast(
                    self.parameters.execution_date, self.parameters.start_date, self.parameters.end_date
                )

            for t in self.orders_time:
                # Reads the minimum power and decides whether an inflexible order should be generated or not
                minimum_power = unit.minimum_power.get_value(t) if unit.minimum_power is not None else 0
                generate_inflexible_order = minimum_power > 0

                # MaximumPower is used to store planned or forced outages (value at 0), in which cases it might be lower than MinimumPower
                if unit.maximum_power.get_value(t) == 0.0 or unit.maximum_power.get_value(t) < minimum_power:
                    if self.parameters.verbose:
                        cfg.logger.warning(
                            f"*** WARNING ***\n MaximumPower is nul or lower than MinimumPower for unit {unit.name} at time {str(t)}. "
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
                    inflexible_order = Order(
                        name=f"inflexible_order_at_{t}_for_unit_{unit.name}",
                        market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=minimum_power,
                        qmin=minimum_power,
                        price=price,
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=self.parameters.execution_date,
                        start_date=t,
                        end_date=t + self.parameters.time_step,
                    )
                    self.dataset.order.append(inflexible_order)

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
                    if self.parameters.verbose:
                        cfg.logger.warning(
                            f"*** WARNING ***\n Negative or null amount of energy in the flexible order to be offered by unit {unit.name} at time {str(t)}. "
                            "The order will therefore not be created."
                        )
                else:
                    # Flexible order
                    self.create_order_and_link(
                        generate_inflexible_order=generate_inflexible_order,
                        inflexible_order=inflexible_order,
                        t=t,
                        unit=unit,
                        order_name=f"flexible_order_at_{t}_for_unit_{unit.name}",
                        q_max=q_max,
                        q_min=0,
                        price=unit.variable_cost.get_value(t),
                        link_name=f"PARENT_CHILDREN_inflexible_flexible_orders_at_{t}_for_unit_{unit.name}",
                    )

                # Reserve orders
                # ==============

                # Automated downward reserves requirements
                if automated_reserves_down_procured.get_value(t) > 0.0:
                    # This order will be the child of the current inflexible order.
                    self.create_order_and_link(
                        generate_inflexible_order=generate_inflexible_order,
                        inflexible_order=inflexible_order,
                        t=t,
                        unit=unit,
                        order_name=f"automated_downward_reserve_order_at_{t}_for_unit_{unit.name}",
                        q_max=automated_reserves_down_procured.get_value(t),
                        q_min=(1 - self.parameters.imposed_proportional_reserves_penalty)
                        * automated_reserves_down_procured.get_value(t),
                        price=unit.variable_cost.get_value(t) - self.parameters.automated_unprocured_reserves_penalty,
                        link_name=f"PARENT_CHILDREN_automated_downward_reserve_inflexible_orders_at_{t}_for_unit_{unit.name}",
                    )

                # Manual downward reserves requirements
                if manual_reserves_down_procured.get_value(t) > 0.0:
                    # This order will be the child of the current inflexible order.
                    self.create_order_and_link(
                        generate_inflexible_order=generate_inflexible_order,
                        inflexible_order=inflexible_order,
                        t=t,
                        unit=unit,
                        order_name=f"manual_downward_reserve_order_at_{t}_for_unit_{unit.name}",
                        q_max=manual_reserves_down_procured.get_value(t),
                        q_min=(1 - self.parameters.imposed_proportional_reserves_penalty)
                        * manual_reserves_down_procured.get_value(t),
                        price=unit.variable_cost.get_value(t) - self.parameters.manual_unprocured_reserves_penalty,
                        link_name=f"PARENT_CHILDREN_manual_downward_reserve_inflexible_orders_at_{t}_for_unit_{unit.name}",
                    )

                # Automated upward reserves requirements
                if automated_reserves_up_procured.get_value(t) > 0.0:
                    # This order will be the child of the current flexible order.
                    self.create_order_and_link(
                        generate_inflexible_order=generate_inflexible_order,
                        inflexible_order=inflexible_order,
                        t=t,
                        unit=unit,
                        order_name=f"automated_upward_reserve_order_at_{t}_for_unit_{unit.name}",
                        q_max=automated_reserves_up_procured.get_value(t),
                        q_min=(1 - self.parameters.imposed_proportional_reserves_penalty)
                        * automated_reserves_up_procured.get_value(t),
                        price=(unit.VariableCost.get_value(t) + self.parameters.automated_unprocured_reserves_penalty),
                        link_name=f"PARENT_CHILDREN_automated_upward_reserve_inflexible_orders_at_{t}_for_unit_{unit.name}",
                    )

                # Manual upward reserves requirements
                if manual_reserves_up_procured.get_value(t) > 0.0:
                    # This order will be the child of the current flexible order.
                    self.create_order_and_link(
                        generate_inflexible_order=generate_inflexible_order,
                        inflexible_order=inflexible_order,
                        t=t,
                        unit=unit,
                        order_name=f"manual_upward_reserve_order_at_{t}_for_unit_{unit.name}",
                        q_max=manual_reserves_up_procured.get_value(t),
                        q_min=(1 - self.parameters.imposed_proportional_reserves_penalty)
                        * manual_reserves_up_procured.get_value(t),
                        price=unit.VariableCost.get_value(t) + self.parameters.manual_unprocured_reserves_penalty,
                        link_name=f"PARENT_CHILDREN_manual_upward_reserve_inflexible_orders_at_{t}_for_unit_{unit.name}",
                    )

    def create_order_and_link(
        self,
        generate_inflexible_order: bool,
        inflexible_order: Order,
        t: DateTime,
        unit: Equipment,
        order_name: str,
        q_max: float,
        q_min: float,
        price: float,
        link_name: str,
    ) -> None:
        order = Order(
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
            execution_date=self.parameters.execution_date,
            start_date=t,
            end_date=t + self.parameters.time_step,
        )
        self.dataset.order.append(order)

        if generate_inflexible_order:
            # Parent-children link between the flexible and inflexible parts
            link = OrderCoupling(name=link_name, orders=[])
            link.coupling_type = CouplingType.PARENT_CHILDREN
            # add the two orders
            link.orders.append(inflexible_order)  # add the parent
            link.orders.append(order)  # add the child
            self.dataset.order_coupling.append(link)
