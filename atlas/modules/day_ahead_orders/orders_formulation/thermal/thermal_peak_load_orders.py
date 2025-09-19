"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Order, OrderCoupling
from atlas.enum import CouplingType, OrderType, Product, ThermalStrategy
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class ThermalPeakLoadOrders:
    # Peak
    @staticmethod
    def formulate_thermal_peak_load_orders(
        dataset: DayAheadOrdersInputDataset, orders_time: list[DateTime], parameters: DayAheadOrdersParameters
    ):
        """
        This function formulates orders for the thermic peak load units. Such orders
        have the particularity of being time-independent, so there is no link between
        two orders that are submitted on different timestamps.
        Peak load units are identified from an attribute of the thermic class.

        Arguments:
        - `dataset`: a dataset
        - `orders_time`: a list of dates at which orders must be formulated.
        - `parameters` a named tuple of parameters, containing the common parameters.

        Returns None
        """

        # Get the list of Thermic instances from the input marker.
        equipments_list = dataset.thermal

        # Filter the peak load instances
        equipments_list = [eqt for eqt in equipments_list if eqt.strategy == ThermalStrategy.PEAK]

        for unit in equipments_list:
            # Get the reserve procurements at the executionDate and collapse them into automated and manual reserves procurements
            automated_reserves_up_procured = unit.afrr_up_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ) + unit.fcr_up_procured.get_forecast(parameters.execution_date, parameters.start_date, parameters.end_date)
            automated_reserves_down_procured = unit.afrr_down_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ) + unit.fcr_down_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            )
            manual_reserves_up_procured = unit.mfrr_up_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ) + unit.rr_up_procured.get_forecast(parameters.execution_date, parameters.start_date, parameters.end_date)
            manual_reserves_down_procured = unit.mfrr_down_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ) + unit.rr_down_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            )

            for t in orders_time:
                # MaximumPower is used to store planned or forced outages (value at 0), in which cases it might be lower than MinimumPower
                if unit.maximum_power.get_value(t) == 0.0 or unit.maximum_power.get_value(
                    t
                ) < unit.minimum_power.get_value(t):
                    if parameters.verbose:
                        cfg.logger.warning(
                            f"*** WARNING ***\n MaximumPower is nul or lower than MinimumPower for unit {unit.name} at time {str(t)}. "
                            "No order will therefore be created."
                        )
                    continue

                # Inflexible order
                # ================

                # Reads the minimum power and decides whether an inflexible order should be generated or not
                minimum_power = unit.minimum_power.get_value(t)
                generate_inflexible_order = minimum_power > 0

                if generate_inflexible_order:
                    # Compute the price
                    Q = minimum_power * (1.0 if unit.minimum_time_on == 0.0 else unit.minimum_time_on)
                    price = unit.startup_cost.get_value(t) / Q + unit.variable_cost.get_value(t)

                    # Create the instance
                    inflexible_order = Order(
                        name=f"inflexible_order_at_{t}_for_unit_{unit.name}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=minimum_power,
                        qmin=minimum_power,
                        price=price,
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(inflexible_order)

                # Flexible order
                # ==============

                # Compute the maximum power of the flexible order
                q_max = (
                    unit.maximum_power.get_value(t)
                    - unit.minimum_power.get_value(t)
                    - manual_reserves_down_procured.get_value(t)
                    - manual_reserves_up_procured.get_value(t)
                    - automated_reserves_down_procured.get_value(t)
                    - automated_reserves_up_procured.get_value(t)
                )

                # We only formulate the order if its maximal power is positive
                if q_max <= 0.0:
                    if parameters.verbose:
                        cfg.logger.warning(
                            f"*** WARNING ***\n Negative or null amount of energy in the flexible order to be offered by unit {unit.name} at time {str(t)}. "
                            "The order will therefore not be created."
                        )

                else:
                    # Flexible order
                    flexible_order = Order(
                        name=f"flexible_order_at_{t}_for_unit_{unit.name}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=q_max,
                        qmin=0,
                        price=unit.variable_cost.get_value(t),
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(flexible_order)

                    if generate_inflexible_order:
                        # Parent-children link between the flexible and inflexible parts
                        link_flexible_inflexible = OrderCoupling(
                            name=f"PARENT_CHILDREN_inflexible_flexible_orders_at_{t}_for_unit_{unit.name}"
                        )
                        link_flexible_inflexible.coupling_type = CouplingType.PARENT_CHILDREN
                        # add the two orders
                        link_flexible_inflexible.orders.append(inflexible_order)  # add the parent
                        link_flexible_inflexible.orders.append(flexible_order)  # add the child
                        dataset.order_coupling.append(link_flexible_inflexible)

                # Reserve orders
                # ==============

                # Automated downward reserves requirements
                if automated_reserves_down_procured.get_value(t) > 0.0:
                    # This order will be the child of the current inflexible order.
                    # Initialize the order object.
                    reserve_bid = Order(
                        name=f"automated_downward_reserve_order_at_{t}_for_unit_{unit.name}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=automated_reserves_down_procured.get_value(t),
                        qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                        * automated_reserves_down_procured.get_value(t),
                        price=unit.variable_cost.get_value(t) - parameters.automated_unprocured_reserves_penalty,
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(reserve_bid)

                    if generate_inflexible_order:
                        # Parent-children link between the flexible and inflexible parts
                        link_reserve_inflexible = OrderCoupling(
                            name=f"PARENT_CHILDREN_automated_downward_reserve_inflexible_orders_at_{t}_for_unit_{unit.name}"
                        )
                        link_reserve_inflexible.coupling_type = CouplingType.PARENT_CHILDREN
                        # add the two orders
                        link_reserve_inflexible.orders.append(inflexible_order)  # add the parent
                        link_reserve_inflexible.orders.append(reserve_bid)  # add the child
                        dataset.order_coupling.append(link_reserve_inflexible)

                # Manual downward reserves requirements
                if manual_reserves_down_procured.get_value(t) > 0.0:
                    # This order will be the child of the current inflexible order.
                    # Initialize the order object.

                    reserve_bid = Order(
                        name=f"manual_downward_reserve_order_at_{t}_for_unit_{unit.name}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=manual_reserves_down_procured.get_value(t),
                        qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                        * manual_reserves_down_procured.get_value(t),
                        price=unit.variable_cost.get_value(t) - parameters.manual_unprocured_reserves_penalty,
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(reserve_bid)

                    if generate_inflexible_order:
                        # Parent-children link between the flexible and inflexible parts
                        link_reserve_inflexible = OrderCoupling(
                            name=f"PARENT_CHILDREN_manual_downward_reserve_inflexible_orders_at_{t}_for_unit_{unit.name}"
                        )
                        link_reserve_inflexible.coupling_type = CouplingType.PARENT_CHILDREN
                        # add the two orders
                        link_reserve_inflexible.orders.append(inflexible_order)  # add the parent
                        link_reserve_inflexible.orders.append(reserve_bid)  # add the child
                        dataset.order_coupling.append(link_reserve_inflexible)

                # Automated upward reserves requirements
                if automated_reserves_up_procured.get_value(t) > 0.0:
                    # This order will be the child of the current flexible order.
                    # Initialize the order object.
                    reserve_bid = Order(
                        name=f"automated_upward_reserve_order_at_{t}_for_unit_{unit.name}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=automated_reserves_up_procured.get_value(t),
                        qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                        * automated_reserves_up_procured.get_value(t),
                        price=(unit.VariableCost.get_value(t) + parameters.automated_unprocured_reserves_penalty),
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(reserve_bid)

                    if generate_inflexible_order:
                        # Parent-children link between the flexible and inflexible parts
                        link_reserve_flexible = OrderCoupling(
                            name=f"PARENT_CHILDREN_automated_upward_reserve_inflexible_orders_at_{t}_for_unit_{unit.name}"
                        )
                        link_reserve_flexible.coupling_type = CouplingType.PARENT_CHILDREN
                        # add the two orders
                        link_reserve_flexible.orders.append(inflexible_order)  # add the parent
                        link_reserve_flexible.orders.append(reserve_bid)  # add the child
                        dataset.order_coupling.append(link_reserve_flexible)

                # Manual upward reserves requirements
                if manual_reserves_up_procured.get_value(t) > 0.0:
                    # This order will be the child of the current flexible order.
                    # Initialize the order object.
                    reserve_bid = Order(
                        name=f"manual_upward_reserve_order_at_{t}_for_unit_{unit.name}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=manual_reserves_up_procured.get_value(t),
                        qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                        * manual_reserves_up_procured.get_value(t),
                        price=unit.VariableCost.get_value(t) + parameters.manual_unprocured_reserves_penalty,
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(reserve_bid)

                    if generate_inflexible_order:
                        # Parent-children link between the flexible and inflexible parts
                        link_reserve_flexible = OrderCoupling(
                            name="PARENT_CHILDREN_manual_upward_reserve_inflexible_orders_at_{}_for_unit_{}".format(
                                t, unit.name
                            )
                        )
                        link_reserve_flexible.coupling_type = CouplingType.PARENT_CHILDREN
                        # add the two orders
                        link_reserve_flexible.orders.append(inflexible_order)  # add the parent
                        link_reserve_flexible.orders.append(reserve_bid)  # add the child
                        dataset.order_coupling.append(link_reserve_flexible)

        return None
