"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math

from pydantic_extra_types.pendulum_dt import DateTime

import atlas.config as cfg
from atlas import Order, OrderCoupling, Thermal, generate_datetimes
from atlas.enum import CouplingType, OrderType, Product
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.dao_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.dao_parameters import DayAheadOrdersParameters


class ThermalUnitOrders:
    # ------ Main order formulation function, for base and intermediate units ------
    @staticmethod
    def formulate_unit_orders(
        online_timeframe: Timeseries,
        unit: Thermal,
        orders_time: list[DateTime],
        dataset: DayAheadOrdersInputDataset,
        parameters: DayAheadOrdersParameters,
        case="",
    ) -> None:
        """
        Formulate orders for one thermic power plant.

        Given a time series of states on which the unit is online (ON_., START and STOP), this function formulates orders according to the
        strategy presented in the documentation.

        Arguments
        `online_timeframe` : a time series over which the unit is online.
        `unit` : the unit for which the orders are formulated.
        `orders_time` : an index of dates over which orders will be formulated.
        `outputMarker` : the marker on which the orders are written
        `p` : a signed tuple of parameters
        `case` : (optional) a string that aims at identifying the price scenario if relevant

        Returns None
        """

        # Determine if the unit is offline or not. A sufficient condition is that the online_timeframe doesn't contain a 1
        # since by construction the unit is ON for at least one time step.
        # JL excludes an online sequence with an incomplete start-up ramp. For now, we will leave it as such.
        offline = True if 0 in online_timeframe.values else False

        # If the unit is offline, no orders are formulated.
        if offline:
            if parameters.verbose:
                """TODO : add the sequence to make message more explicit"""
                cfg.logger.info(f"Unit {unit.name} is offline. No orders have been formulated for this unit")
            return None

        # If not offline, start the configuration of variables necessary for order formulation

        # Configuration of variables for orders' formulation
        ## Get the reserve procurements at the executionDate and collapse them into automated and manual reserves procurements

        automated_reserves_up_procured = Timeseries.from_index(
            parameters.start_date, parameters.time_step, parameters.end_date, 0
        )
        automated_reserves_down_procured = Timeseries.from_index(
            parameters.start_date, parameters.time_step, parameters.end_date, 0
        )
        manual_reserves_up_procured = Timeseries.from_index(
            parameters.start_date, parameters.time_step, parameters.end_date, 0
        )
        manual_reserves_down_procured = Timeseries.from_index(
            parameters.start_date, parameters.time_step, parameters.end_date, 0
        )

        if unit.afrr_up_procured and unit.fcr_up_procured:
            automated_reserves_up_procured = unit.afrr_up_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ) + unit.fcr_up_procured.get_forecast(parameters.execution_date, parameters.start_date, parameters.end_date)
        if unit.afrr_down_procured and unit.fcr_down_procured:
            automated_reserves_down_procured = unit.afrr_down_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ) + unit.fcr_down_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            )
        if unit.mfrr_up_procured and unit.rr_up_procured:
            manual_reserves_up_procured = unit.mfrr_up_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ) + unit.rr_up_procured.get_forecast(parameters.execution_date, parameters.start_date, parameters.end_date)
        if unit.mfrr_down_procured and unit.rr_down_procured:
            manual_reserves_down_procured = unit.mfrr_down_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            ) + unit.rr_down_procured.get_forecast(
                parameters.execution_date, parameters.start_date, parameters.end_date
            )

        ## Get the unit-specific parameters:
        T_start = int(math.floor(unit.startup_duration / parameters.time_step))
        T_stop = int(math.floor(unit.shutdown_duration / parameters.time_step))
        q_min = unit.minimum_power.max()

        ## See whether the unit will bid inflexible orders over the whole orders_time sequence:
        null_minimum_power = all(p in unit.minimum_power.index for p in orders_time)

        ## See whether there is a startup or not. Used to know if we need to amortise startup cost over the inflexible
        # orders or not.
        startup = True if 2 in online_timeframe.values else False
        # if T_start > 0:
        #     startup = True if 2 in online_timeframe.Values else False
        # else:
        #     # Another way to check the startup, less efficient but more robust
        #     startup = False
        #     for t in list(online_timeframe.Index)[:-1]:
        #         t_next = t.AddMinutes(p.time_step)
        #         if online_timeframe.get_value(t_next) - online_timeframe.get_value(t) == 1:
        #             startup = True

        ## See whether the ramps are complete or not
        T_startSD_in_sim = False
        if 3 in online_timeframe.values:
            for t in list(online_timeframe.index)[:-1]:
                t_next = t + parameters.time_step
                if online_timeframe.get_value(t_next) - online_timeframe.get_value(t) == 2:
                    # passage from 1 to 3 in sequence, indicating the beginning of a shutdown
                    T_startSD_in_sim = True

        T_endSU_in_sim = False
        if startup:
            for t in list(online_timeframe.index)[:-1]:
                t_next = t + parameters.time_step
                if online_timeframe.get_value(t) - online_timeframe.get_value(t_next) == 1:
                    # passage from 2 to 1 in sequence, indicating the end of a startup
                    T_endSU_in_sim = True

        ## Extract K_start, K_stop.
        # K_start is the number of timesteps actually startup within the simulation timeframe (shorter than overall
        # timeframe used for computing states sequences).
        # K_start is the number of timesteps actually shutdown within the simulation timeframe (shorter than overall
        # timeframe used for computing states sequences).

        # Compute K_start and K_stop
        K_start, K_stop = 0, 0
        m, n = 0, 0
        for t in orders_time:
            if t in online_timeframe.index and online_timeframe.get_value(t) == 2:
                m += 1
            elif t in online_timeframe.index and online_timeframe.get_value(t) == 3:
                n += 1

        # Update the values
        K_start += m
        K_stop += n

        ## Definition of the time frames.
        ### Ramping timeframes: by construction, the associated start_time_frame and stop_time_frame
        # will be one time step longer than the usual start-up and shutdown periods.

        # Getting the starting date of the time frames.
        if K_start > 0 or K_stop > 0:
            for t in orders_time:
                if t in online_timeframe.index and online_timeframe.get_value(t) == 2:
                    begin_of_startTimeFrame = t
                    break
            for t in orders_time:
                if t in online_timeframe.index and online_timeframe.get_value(t) == 3:
                    begin_of_stopTimeFrame = t
                    break

        if K_start > 0:
            start_time_frame = generate_datetimes(
                begin_of_startTimeFrame, begin_of_startTimeFrame + K_start * parameters.time_step, parameters.time_step
            )
        if K_stop > 0:  # Shift by one time step because the time frame encompasses the last time step in the ON state
            # and remove one index because the last time step (null power) is formally excluded.
            stop_time_frame = generate_datetimes(
                begin_of_stopTimeFrame - parameters.time_step,
                begin_of_stopTimeFrame + (K_stop - 1) * parameters.time_step,
                parameters.time_step,
            )

        # In corner cases on the border of the time frame, remove excess time indexes.
        if K_start > 0:
            start_time_frame = [t for t in start_time_frame if t in orders_time]
        if K_stop > 0:
            stop_time_frame = [t for t in stop_time_frame if t in orders_time]

        ### FlexibleTimeFrame : all time indexes labelled with a 1 that are not in the start_time_frame or stop_time_frame
        # The potential overlapping is due to the fact that, by convention, the start and stop timeFrames are one time
        # step longer than the usual start-up and shutdown periods.
        # In case of startup: the last startup timestep, at Pmin, is the first one of the stable state sequence (state = 1),
        # to be removed from the flexible_time_frame.
        # In case of shutdown: the first shutdown timestep, at Pmin, is the last one of the previous stable state sequence,
        # to be removed from the flexible_time_frame.
        flexible_time_frame = []
        for t in orders_time:
            if t in online_timeframe.index and online_timeframe.get_value(t) == 1:
                flexible_time_frame.append(t)

        # Sanity check : the flexible_time_frame only contains timestamps within the orders_time time frame.
        flexible_time_frame = [t for t in flexible_time_frame if t in orders_time]

        # Remove potential overlapping time steps with the ramping timeframes.
        if K_start > 0:
            flexible_time_frame = [t for t in flexible_time_frame if t not in start_time_frame]
        if K_stop > 0:
            flexible_time_frame = [t for t in flexible_time_frame if t not in stop_time_frame]
            if K_start > 0:
                # Deal with the last corner case where the unit remains online for one time step. In this case, the overlapping time steps
                # between the start_time_frame and stop_time_frame is a singleton and by convention we remove this time step from the shutdown time frame.
                overlapping_time_steps = set(start_time_frame) & set(stop_time_frame)
                if len(overlapping_time_steps) == 1:
                    stop_time_frame = [t for t in stop_time_frame if t not in overlapping_time_steps]

        ## Inflexible timeframe
        inflexible_time_frame = online_timeframe.index

        # Formulate orders only if the unit is online

        # ------------------------------------------------------- #
        #                                                         #
        #                   Flexible layer                        #
        #                                                         #
        # ------------------------------------------------------- #
        # Loop over the flexible_time_frame to create the flexible orders first, formulated no matter what.
        for t in flexible_time_frame:
            # Part 1: flexible order
            # Compute the maximum amount to be offered.
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
                # Flexible part of the order
                flexible_part = Order(
                    name=f"flexible_order_at_{t}_for_unit_{unit.name}_with_scenario_{case}",
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
                dataset.order.append(flexible_part)

            # Part 2: reserve requirement orders
            # Automated downward reserves requirements
            if automated_reserves_down_procured.get_value(t) > 0.0:
                # This order will be the child of the current inflexible order.
                # Initialize the order object.
                reserve_bid = Order(
                    name=f"automated_downward_reserve_order_at_{t}_for_unit_{unit.name}_with_scenario_{case}",
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

            # Manual downard reserves requirements
            if manual_reserves_down_procured.get_value(t) > 0.0:
                # This order will be the child of the current inflexible order.
                # Initialize the order object.
                reserve_bid = Order(
                    name=f"manual_downward_reserve_order_at_{t}_for_unit_{unit.name}_with_scenario_{case}",
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

            # Automated upward reserves requirements
            if automated_reserves_up_procured.get_value(t) > 0.0:
                # This order will be the child of the current flexible order.
                # Initialize the order object.
                reserve_bid = Order(
                    name=f"automated_upward_reserve_order_at_{t}_for_unit_{unit.name}_with_scenario_{case}",
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=automated_reserves_up_procured.get_value(t),
                    qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                    * automated_reserves_up_procured.get_value(t),
                    price=unit.variable_cost.get_value(t) + parameters.automated_unprocured_reserves_penalty,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(reserve_bid)

            # Manual upward reserves requirements
            if manual_reserves_up_procured.get_value(t) > 0.0:
                # This order will be the child of the current flexible order.
                # Initialize the order object.
                reserve_bid = Order(
                    name=f"manual_upward_reserve_order_at_{t}_for_unit_{unit.name}_with_scenario_{case}",
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=manual_reserves_up_procured.get_value(t),
                    qmin=(1 - parameters.imposed_proportional_reserves_penalty)
                    * manual_reserves_up_procured.get_value(t),
                    price=unit.variable_cost.get_value(t) + parameters.manual_unprocured_reserves_penalty,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(reserve_bid)

        # ------------------------------------------------------- #
        #                                                         #
        #                   Inflexible layer                      #
        #                                                         #
        # ------------------------------------------------------- #
        # Add inflexible orders as a base if the minimum power of the unit is non-zero at least once during the day.
        # Add the corresponding parent/child couplings between the inflexible and flexible layers.
        if not null_minimum_power:
            # Compute the ramping gradients
            if T_start == 0:
                q_step_up = q_min
            else:
                q_step_up = q_min / T_start

            if T_stop == 0:
                q_step_down = q_min
            else:
                q_step_down = q_min / T_stop

            # Initialize the overall inflexible quantity offered, on which the startup cost will be spread afterwards
            Q = 0

            # Loop over the inflexible_time_frame to create the orders.
            inflexible_orders = []

            # Part 1: Startup orders
            # Does not create bids if there is not at least one stable state within the online sequence (prevents creating
            # unfinished startup ramps towards Pmin within the simulation timeframe for border case reasons.
            if K_start > 0:
                for t, i in zip(start_time_frame, range(K_start + 1), strict=False):
                    # Initialize the bid.

                    # Compute the parameters of the order
                    if T_endSU_in_sim:
                        q_sell = round((T_start - K_start + i) * q_step_up)
                    else:
                        q_sell = round(i * q_step_up)

                    bid_output = Order(
                        name=f"startup_ramp_order_at_{t}_for_unit_{unit.name}_with_scenario_{case}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=q_sell,
                        qmin=q_sell,
                        price=unit.variable_cost.get_value(t),
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(bid_output)

                    inflexible_orders.append(bid_output)
                    Q += q_sell

            # Part 2: Shutdown orders
            # Does not create bids if there is not at least one stable state within the online sequence (prevents creating
            # shutdown ramps without the starting point at Pmin within the simulation timeframe for border case reasons.
            if K_stop > 0:
                for t, i in zip(stop_time_frame, range(K_stop + 1), strict=False):
                    # Initialize the bid.

                    # Compute the quantities to be sold.
                    if T_startSD_in_sim:
                        q_sell = round((T_stop - i) * q_step_down)
                    else:
                        q_sell = round(q_min - (T_stop - K_stop + i) * q_step_down)

                    bid_output = Order(
                        name=f"shutdown_ramp_order_at_{t}_for_unit_{unit.name}_with_scenario_{case}",
                        market_area=unit.portfolio.market_area,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=q_sell,
                        qmin=q_sell,
                        price=round(unit.variable_cost.get_value(t), 2),
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=parameters.execution_date,
                        start_date=t,
                        end_date=t + parameters.time_step,
                    )
                    dataset.order.append(bid_output)

                    inflexible_orders.append(bid_output)
                    Q += q_sell

            # Part 3: inflexible orders at Pmin
            for t in flexible_time_frame:
                # Initialize the inflexible order object.
                bid_output = Order(
                    name=f"order_at_{t}_for_unit_{unit.name}_under_price_{case}",
                    market_area=unit.portfolio.market_area,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=unit.minimum_power.get_value(t),
                    qmin=unit.minimum_power.get_value(t),
                    price=round(unit.variable_cost.get_value(t), 2),
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=parameters.execution_date,
                    start_date=t,
                    end_date=t + parameters.time_step,
                )
                dataset.order.append(bid_output)

                inflexible_orders.append(bid_output)
                Q += unit.minimum_power.get_value(t)

                # Check the existence of flexible bids to be linked by a parent-child coupling
                flexible_types = [
                    "flexible_order",
                    "manual_upward_reserve_order",
                    "automated_upward_reserve_order",
                    "manual_downward_reserve_order",
                    "automated_downward_reserve_order",
                ]
                for flex_type in flexible_types:
                    config_bid_name = f"_at_{t}_for_unit_{unit.name}_with_scenario_{case}"
                    flexible_bid_name = flex_type + config_bid_name
                    flexible_bid = next((bid for bid in dataset.order if bid.name == flexible_bid_name), None)
                    if flexible_bid is not None:
                        ThermalUnitOrders.create_parent_child_link(dataset, bid_output, flexible_bid, case, unit, t)

            # Part 4: configure the identical_ratio link between all inflexible orders
            date = inflexible_time_frame[0]
            coupling = OrderCoupling(
                name=f"IDENTICAL_RATIO_inflexible_orders_for_unit_{unit.name}_starting_at_{date}_with_scenario_{case}",
                coupling_type=CouplingType.IDENTICAL_RATIO,
                orders=[],
            )
            for order in inflexible_orders:
                coupling.orders.append(order)
            dataset.order_coupling.append(coupling)

            # Part 5 : if startup, amortise startup cost on all inflexible layer
            amortized_cost = round(unit.startup_cost.get_value(t) / Q, 2)
            for order in inflexible_orders:
                # Add the spreading of start up cost only if the startup is complete within the sequence
                if startup and T_endSU_in_sim:
                    order.price += amortized_cost
                else:
                    order.price -= amortized_cost

    @staticmethod
    def create_parent_child_link(
        dataset: DayAheadOrdersInputDataset, parent_bid: Order, child_bid: Order, case: str, unit: Thermal, t: DateTime
    ) -> None:
        # Add parent-children link between the flexible and inflexible parts
        link_flexible_inflexible = OrderCoupling(
            name=f"PARENT_CHILDREN_inflexible_flexible_orders_at_{t}_for_unit_{unit.name}_with_scenario_{case}",
            coupling_type=CouplingType.PARENT_CHILDREN,
            orders=[],
        )
        # add the two orders
        link_flexible_inflexible.orders.append(parent_bid)
        link_flexible_inflexible.orders.append(child_bid)
