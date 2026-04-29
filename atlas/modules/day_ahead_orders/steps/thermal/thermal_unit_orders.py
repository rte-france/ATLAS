"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
from typing import cast

import pendulum
import polars as pl
from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import CouplingType, OrderType, Product
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.timing import generate_datetimes


class ThermalUnitOrders:
    """Main order formulation function, for base and intermediate units"""

    def __init__(self, orders_time: list[DateTime], parameters: DayAheadOrdersParameters):
        """
        :param orders_time: a list of dates over which orders will be formulated.
        :type orders_time: list[DateTime]
        :param parameters: the parameters
        :type parameters: DayAheadOrdersParameters
        """
        self.orders_time = orders_time
        self.parameters = parameters

    def formulate_unit_orders(
        self,
        online_timeframe: Timeseries,
        unit: ThermalDAO,
        case: str = "",
    ) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        Formulate orders for one thermic power plant.

        Given a time series of states on which the unit is online (ON_., START and STOP), this function formulates orders according to the
        strategy presented in the documentation.

        :param online_timeframe: a time series over which the unit is online.
        :type online_timeframe: Timeseries
        :param unit: the unit for which the orders are formulated.
        :type unit: ThermalDAO
        :param case: (optional) a string that aims at identifying the price scenario if relevant
        :type case: str
        :return: orders and order couplings generated for this unit
        :rtype: tuple[list[OrderDAO], list[OrderCouplingDAO]]
        """
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        scenario_suffix = f"_with_price_{case}" if case else "_with_price"

        # Determine if the unit is offline or not. A sufficient condition is that the online_timeframe doesn't contain a 1
        # since by construction the unit is ON for at least one time step.
        # JL excludes an online sequence with an incomplete start-up ramp. For now, we will leave it as such.
        offline = True if 0 in online_timeframe.values else False

        # If the unit is offline, no orders are formulated.
        if offline:
            """TODO : add the sequence to make message more explicit"""
            cfg.logger.debug(f"Unit {unit.name} is offline. No orders have been formulated for this unit")
            return orders, couplings

        # If not offline, start the configuration of variables necessary for order formulation

        # Configuration of variables for orders' formulation
        ## Get the reserve procurements at the executionDate and collapse them into automated and manual reserves procurements

        start = self.parameters.temporal.start_date
        end = self.parameters.temporal.end_date
        step = self.parameters.temporal.timestep
        ed = self.parameters.temporal.execution_date

        _default = Timeseries.from_index(start, step, end, 0)

        def _get(attr: str) -> Timeseries:
            source = getattr(unit, attr)
            return source.get_forecast(ed, start, end) if source else _default

        automated_reserves_up_procured = _get("afrr_up_procured") + _get("fcr_up_procured")
        automated_reserves_down_procured = _get("afrr_down_procured") + _get("fcr_down_procured")
        manual_reserves_up_procured = _get("mfrr_up_procured") + _get("rr_up_procured")
        manual_reserves_down_procured = _get("mfrr_down_procured") + _get("rr_down_procured")

        ## Get the unit-specific parameters:
        T_start = int(math.floor(unit.startup_duration / self.parameters.temporal.timestep))
        T_stop = int(math.floor(unit.shutdown_duration / self.parameters.temporal.timestep))
        q_min = unit.minimum_power.max()

        ## See whether the unit will bid inflexible orders over the whole orders_time sequence:
        if isinstance(unit.minimum_power, LazyTimeseries):
            min_power = unit.minimum_power.collect()
        else:
            min_power = cast(Timeseries, unit.minimum_power)
            if min_power.filter(self.orders_time, inplace=False).dataframe["value"].min() == 0:
                null_minimum_power = True
            else:
                null_minimum_power = False

        ## See whether there is a startup or not. Used to know if we need to amortise startup cost over the inflexible
        # orders or not.
        startup = True if 2 in online_timeframe.values else False

        ## See whether the ramps are complete or not
        T_startSD_in_sim = False
        if 3 in online_timeframe.values:
            index = list(online_timeframe.index)
            for t, t_next in zip(index[:-1], index[1:], strict=False):
                if online_timeframe.get_value(t_next) - online_timeframe.get_value(t) == 2:
                    T_startSD_in_sim = True
                    break

        T_endSU_in_sim = False
        if startup:
            index = list(online_timeframe.index)
            for t, t_next in zip(index[:-1], index[1:], strict=False):
                if online_timeframe.get_value(t) - online_timeframe.get_value(t_next) == 1:
                    T_endSU_in_sim = True
                    break

        ## Extract K_start, K_stop.
        # K_start is the number of timesteps actually startup within the simulation timeframe (shorter than overall
        # timeframe used for computing states sequences).
        # K_start is the number of timesteps actually shutdown within the simulation timeframe (shorter than overall
        # timeframe used for computing states sequences).

        # Compute K_start and K_stop
        K_start, K_stop = 0, 0
        m, n = 0, 0
        online_index_set = set(online_timeframe.index)
        for t in self.orders_time:
            if t in online_index_set:
                v = online_timeframe.get_value(t)
                if v == 2:
                    m += 1
                elif v == 3:
                    n += 1

        # Update the values
        K_start += m
        K_stop += n

        ## Definition of the time frames.
        ### Ramping timeframes: by construction, the associated start_time_frame and stop_time_frame
        # will be one time step longer than the usual start-up and shutdown periods.

        # Getting the starting date of the time frames.
        if K_start > 0 or K_stop > 0:
            for t in self.orders_time:
                if t in online_index_set and online_timeframe.get_value(t) == 2:
                    begin_of_startTimeFrame = t
                    break
            for t in self.orders_time:
                if t in online_index_set and online_timeframe.get_value(t) == 3:
                    begin_of_stopTimeFrame = t
                    break

        if K_start > 0:
            start_time_frame = generate_datetimes(
                begin_of_startTimeFrame,
                begin_of_startTimeFrame + K_start * self.parameters.temporal.timestep,
                self.parameters.temporal.timestep,
            )
        if K_stop > 0:  # Shift by one time step because the time frame encompasses the last time step in the ON state
            # and remove one index because the last time step (null power) is formally excluded.
            stop_time_frame = generate_datetimes(
                begin_of_stopTimeFrame - self.parameters.temporal.timestep,
                begin_of_stopTimeFrame + (K_stop - 1) * self.parameters.temporal.timestep,
                self.parameters.temporal.timestep,
            )

        # In corner cases on the border of the time frame, remove excess time indexes.
        if K_start > 0:
            start_time_frame = [t for t in start_time_frame if t in self.orders_time]
        if K_stop > 0:
            stop_time_frame = [t for t in stop_time_frame if t in self.orders_time]

        ### FlexibleTimeFrame : all time indexes labelled with a 1 that are not in the start_time_frame or stop_time_frame
        # The potential overlapping is due to the fact that, by convention, the start and stop timeFrames are one time
        # step longer than the usual start-up and shutdown periods.
        # In case of startup: the last startup timestep, at Pmin, is the first one of the stable state sequence (state = 1),
        # to be removed from the flexible_time_frame.
        # In case of shutdown: the first shutdown timestep, at Pmin, is the last one of the previous stable state sequence,
        # to be removed from the flexible_time_frame.
        flexible_time_frame: list[DateTime] = []
        for t in self.orders_time:
            if t in online_index_set and online_timeframe.get_value(t) == 1:
                flexible_time_frame.append(t)

        # Sanity check : the flexible_time_frame only contains timestamps within the orders_time time frame.
        flexible_time_frame = [t for t in flexible_time_frame if t in self.orders_time]

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

        # Pre-compute vectorised q_max before the flexible loop
        time_filter = pl.col("time").is_in(flexible_time_frame)
        q_max_ts = (
            Timeseries(unit.maximum_power.timeseries.filter(time_filter))
            - Timeseries(unit.minimum_power.timeseries.filter(time_filter))
            - Timeseries(manual_reserves_down_procured.timeseries.filter(time_filter))
            - Timeseries(manual_reserves_up_procured.timeseries.filter(time_filter))
            - Timeseries(automated_reserves_down_procured.timeseries.filter(time_filter))
            - Timeseries(automated_reserves_up_procured.timeseries.filter(time_filter))
        )

        prop_pen = 1 - self.parameters.proportional_reserves_penalty
        auto_pen = self.parameters.automated_unprocured_reserves_penalty
        man_pen = self.parameters.manual_unprocured_reserves_penalty

        # ------------------------------------------------------- #
        #                                                         #
        #                   Flexible layer                        #
        #                                                         #
        # ------------------------------------------------------- #
        # Loop over the flexible_time_frame to create the flexible orders first, formulated no matter what.
        for t in flexible_time_frame:
            # Part 1: flexible order
            # Compute the maximum amount to be offered.
            q_max = q_max_ts.get_value(t)
            var_cost = unit.variable_cost.get_value(t)
            auto_down = automated_reserves_down_procured.get_value(t)
            man_down = manual_reserves_down_procured.get_value(t)
            auto_up = automated_reserves_up_procured.get_value(t)
            man_up = manual_reserves_up_procured.get_value(t)

            # We only formulate the order if its maximal power is positive
            if q_max <= 0.0:
                cfg.logger.warning(
                    f"Negative or null amount of energy in the flexible order to be offered by unit {unit.name} at time {str(t)}. "
                    "The order will therefore not be created."
                )
            else:
                # Flexible part of the order
                flexible_part = OrderDAO(
                    name=f"flexible_order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}{scenario_suffix}",
                    market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=q_max,
                    qmin=0,
                    price=var_cost,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=self.parameters.temporal.execution_date,
                    start_date=t,  # type: ignore [arg-type]
                    end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                )
                orders.append(flexible_part)

            # Part 2: reserve requirement orders
            # Automated downward reserves requirements
            if auto_down > 0.0:
                # This order will be the child of the current inflexible order.
                reserve_bid = OrderDAO(
                    name=f"automated_downward_reserve_order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}{scenario_suffix}",
                    market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=auto_down,
                    qmin=prop_pen * auto_down,
                    price=var_cost - auto_pen,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=self.parameters.temporal.execution_date,
                    start_date=t,  # type: ignore [arg-type]
                    end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                )
                orders.append(reserve_bid)

            # Manual downard reserves requirements
            if man_down > 0.0:
                # This order will be the child of the current inflexible order.
                reserve_bid = OrderDAO(
                    name=f"manual_downward_reserve_order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}{scenario_suffix}",
                    market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=man_down,
                    qmin=prop_pen * man_down,
                    price=var_cost - man_pen,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=self.parameters.temporal.execution_date,
                    start_date=t,  # type: ignore [arg-type]
                    end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                )
                orders.append(reserve_bid)

            # Automated upward reserves requirements
            if auto_up > 0.0:
                # This order will be the child of the current flexible order.
                reserve_bid = OrderDAO(
                    name=f"automated_upward_reserve_order_at_{t}_for_unit_{unit.name}{scenario_suffix}",
                    market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=auto_up,
                    qmin=prop_pen * auto_up,
                    price=var_cost + auto_pen,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=self.parameters.temporal.execution_date,
                    start_date=t,  # type: ignore [arg-type]
                    end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                )
                orders.append(reserve_bid)

            # Manual upward reserves requirements
            if man_up > 0.0:
                # This order will be the child of the current flexible order.
                reserve_bid = OrderDAO(
                    name=f"manual_upward_reserve_order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}{scenario_suffix}",
                    market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=man_up,
                    qmin=prop_pen * man_up,
                    price=var_cost + man_pen,
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=self.parameters.temporal.execution_date,
                    start_date=t,  # type: ignore [arg-type]
                    end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                )
                orders.append(reserve_bid)

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
            Q = 0.0

            # Loop over the inflexible_time_frame to create the orders.
            inflexible_orders = []

            # Part 1: Startup orders
            # Does not create bids if there is not at least one stable state within the online sequence (prevents creating
            # unfinished startup ramps towards Pmin within the simulation timeframe for border case reasons.
            if K_start > 0:
                for t, i in zip(start_time_frame, range(K_start + 1), strict=False):
                    # Compute the parameters of the order
                    if T_endSU_in_sim:
                        q_sell = round((T_start - K_start + i) * q_step_up)
                    else:
                        q_sell = round(i * q_step_up)

                    bid_output = OrderDAO(
                        name=f"startup_ramp_order_at_{t}_for_unit_{unit.name}{scenario_suffix}",
                        market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=q_sell,
                        qmin=q_sell,
                        price=unit.variable_cost.get_value(t),
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=self.parameters.temporal.execution_date,
                        start_date=t,  # type: ignore [arg-type]
                        end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                    )
                    orders.append(bid_output)

                    inflexible_orders.append(bid_output)
                    Q += q_sell

            # Part 2: Shutdown orders
            # Does not create bids if there is not at least one stable state within the online sequence (prevents creating
            # shutdown ramps without the starting point at Pmin within the simulation timeframe for border case reasons.
            if K_stop > 0:
                for t, i in zip(stop_time_frame, range(K_stop + 1), strict=False):
                    # Compute the quantities to be sold.
                    if T_startSD_in_sim:
                        q_sell = round((T_stop - i) * q_step_down)
                    else:
                        q_sell = round(q_min - (T_stop - K_stop + i) * q_step_down)

                    bid_output = OrderDAO(
                        name=f"shutdown_ramp_order_at_{t}_for_unit_{unit.name}{scenario_suffix}",
                        market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                        portfolio=unit.portfolio,
                        equipment=unit,
                        qmax=q_sell,
                        qmin=q_sell,
                        price=round(unit.variable_cost.get_value(t), 2),
                        product=Product.DayAhead,
                        order_type=OrderType.Sell,
                        is_agent_tso=False,
                        execution_date=self.parameters.temporal.execution_date,
                        start_date=t,  # type: ignore [arg-type]
                        end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                    )
                    orders.append(bid_output)

                    inflexible_orders.append(bid_output)
                    Q += q_sell

            # Part 3: inflexible orders at Pmin
            # TODO: should be inflexible_time_frame, but not working currently for format reasons
            for t in inflexible_time_frame:
                t = pendulum.instance(t)
                min_p = unit.minimum_power.get_value(t)
                var_cost = unit.variable_cost.get_value(t)
                name = (
                    f"order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}_under_price_{case}"
                    if case
                    else f"order_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}_under_price"
                )
                bid_output = OrderDAO(
                    name=name,
                    market_area=unit.portfolio.market_area if unit.portfolio is not None else None,
                    portfolio=unit.portfolio,
                    equipment=unit,
                    qmax=min_p,
                    qmin=min_p,
                    price=round(var_cost, 2),
                    product=Product.DayAhead,
                    order_type=OrderType.Sell,
                    is_agent_tso=False,
                    execution_date=self.parameters.temporal.execution_date,
                    start_date=t,  # type: ignore [arg-type]
                    end_date=t + self.parameters.temporal.timestep,  # type: ignore [arg-type]
                )
                orders.append(bid_output)

                inflexible_orders.append(bid_output)
                Q += min_p

                # Check the existence of flexible bids to be linked by a parent-child coupling
                flexible_types = [
                    "flexible_order",
                    "manual_upward_reserve_order",
                    "automated_upward_reserve_order",
                    "manual_downward_reserve_order",
                    "automated_downward_reserve_order",
                ]
                for flex_type in flexible_types:
                    config_bid_name = f"_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}{scenario_suffix}"
                    flexible_bid_name = flex_type + config_bid_name
                    flexible_bid = next((bid for bid in orders if bid.name == flexible_bid_name), None)
                    if flexible_bid is not None:
                        # Add parent-children link between the flexible and inflexible parts
                        couplings.append(
                            OrderCouplingDAO(
                                name=f"parent_children_inflexible_flexible_orders_at_{t.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{unit.name}{scenario_suffix}",
                                coupling_type=CouplingType.PARENT_CHILDREN,
                                orders=[bid_output, flexible_bid],
                            )
                        )

            # Part 4: configure the identical_ratio link between all inflexible orders
            date = pendulum.DateTime.instance(inflexible_time_frame[0])
            couplings.append(
                OrderCouplingDAO(
                    name=f"identical_ratio_inflexible_orders_for_unit_{unit.name}_starting_at_{date.format('DD_MM_YYYY_HH_mm_ss')}{scenario_suffix}",
                    coupling_type=CouplingType.IDENTICAL_RATIO,
                    orders=inflexible_orders,  # type: ignore [arg-type]
                )
            )

            # Part 5 : if startup, amortise startup cost on all inflexible layer
            amortized_cost = round(unit.startup_cost.get_value(t) / Q, 2)
            for order in inflexible_orders:
                # Add the spreading of start up cost only if the startup is complete within the sequence
                if startup and T_endSU_in_sim:
                    order.price += amortized_cost
                else:
                    order.price -= amortized_cost

        return orders, couplings

    def extract_online_sequences(self, states_sequence: Timeseries, case: str = "") -> list[tuple[Timeseries, str]]:
        """
        A helper function that extracts online sequence based on a thermal unit states sequence.
        This in particular allows for the formulation of order on several sub-intervals if the unit
        were to be restarted over the orders_time time frame.

        :param states_sequence: a time series containing the state sequence of the unit.
        :type states_sequence: Timeseries
        :param case: (optional) a string that aims at identifying the price scenario if relevant
        :type case: str
        :return: a list of tuples (timeseries, case_name), each timeseries containing a sequence over which the unit is online empty if the unit is offline over the whole time frame
        :rtype: list[tuple[Timeseries, str]]
        """
        # Get the time steps for which the unit is online (defined as a non-zero state):
        # Consistency of the online states wrt the minimum duration is ensured by definition of the
        # determine_baseload_states_sequence function.
        online_at_t = sorted(
            [pendulum.instance(dt) for dt in set(self.orders_time).intersection(states_sequence.index)]
        )

        # Based on these time steps, deduce the intervals.
        # The intervals bounds are retrieved by comparing the total minutes between to time steps :
        # if the total number of minutes is greater that time_step, then the time steps i and i+1 correspond to bounds of two distinct intervals
        intervals = []
        if online_at_t:
            intervals.append(online_at_t[0])
            if len(online_at_t) >= 2:
                for i in range(len(online_at_t) - 1):
                    if not (online_at_t[i + 1] - online_at_t[i]) == self.parameters.temporal.timestep:
                        intervals.append(online_at_t[i])
                        intervals.append(online_at_t[i + 1])
            intervals.append(online_at_t[-1])  # Add the element. This allows for potential singletons

        # Based on the interval boundaries, retrieve the intervals
        # If the unit is online over the whole orders_time time frame, then only one interval is generated
        # Otherwise all intervals are generated, using the fact that by construction, there is an even
        # number of time steps in the intervals list.
        list_of_online_timeframes: list[tuple[Timeseries, str]] = []
        if intervals:
            intervals.sort()
            for i in range(int(len(intervals) / 2)):
                window = states_sequence.slice(intervals[2 * i], intervals[2 * i + 1], "both", False)
                # don't add duplicates
                if len(list_of_online_timeframes) == 0:
                    list_of_online_timeframes.append((window, case))
                elif all(window != ts for ts, _ in list_of_online_timeframes):
                    list_of_online_timeframes.append((window, case))

        return list_of_online_timeframes
