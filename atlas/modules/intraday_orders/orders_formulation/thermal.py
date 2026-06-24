"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import CouplingType, OrderType, ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.input_objects.thermal import ThermalIDO
from atlas.modules.intraday_orders.models.thermal_order_window import ThermalOrderWindow
from atlas.modules.intraday_orders.models.window_type import WindowType
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


def compare_planning(equipment: ThermalIDO, orders_timestamps: list[DateTime], parameters: IntradayOrdersParameters):
    """
    TODO: rewrite docstring properly
    For a given unit, compare the latest generation planning and to the new one resulting from an optimization
    return a time series of -2, -1, 0, 1,2 depending on the delta between the two planning

    - `unit` : a thermal unit  from an Atlas input Marker from day-ahead process or a previous ID process => previous_p
    - results_optim : an output of the optimization process giving the latest optimal planning of all the units => new_p
    - orders_time : a sequence of date over which we want to create orders

    return a time series over orders_time with -2,-1,0,1,2 (see comments below for the meaning)

    """
    # Read the latest planning in the input Marker
    # previous_p=unit.Power.GetForecast(execution_date,orders_time[0],orders_time[-1])
    previous_p = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity

    # Read the new optimal planning resulting from the optimization
    # TODO: [equipment] change based on optimization results format
    new_p = equipment.id_po_for_orders.get_forecast(
        parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
    )
    # We create an empty list to store the value to be filled in the output time series
    delta_planning_values = []

    # For each date in the list of orders_time, we compare the two plannings
    # and add the correct comparison code in the list
    for t in orders_timestamps:
        if new_p.get_value(t) > previous_p.get_value(t):
            if previous_p.get_value(t) >= equipment.minimum_power.get_value(t):
                # New power is above the previous one but both are started up => code 2
                delta_planning_values.append(2)
            elif new_p.get_value(t) >= equipment.minimum_power.get_value(t):
                # New power is started up but not the previous one => code 1
                delta_planning_values.append(1)
            else:
                # In this case, both planning are below Pmin: for now it is not considered
                delta_planning_values.append(0)
        elif new_p.get_value(t) < previous_p.get_value(t):
            if new_p.get_value(t) >= equipment.minimum_power.get_value(t):
                # New power is below the previous one but both are started up=> code -2
                delta_planning_values.append(-2)
            elif previous_p.get_value(t) >= equipment.minimum_power.get_value(t):
                # Previous power is started up but not the new one => code -1
                delta_planning_values.append(-1)
            else:
                # In this case, both planning are below Pmin: for now it is not considered
                delta_planning_values.append(0)
        else:
            delta_planning_values.append(0)  # both power are identical => code 0

    # Creation of a time series over orders_time with the comparing code
    delta_planning = Timeseries()
    for t, delta_planning_value in zip(orders_timestamps, delta_planning_values, strict=False):
        delta_planning.set_value(t, delta_planning_value)

    return delta_planning


def extract_sequences_from_delta_planning(
    equipment: ThermalIDO, delta_planning: Timeseries, orders_time: list[DateTime], parameters: IntradayOrdersParameters
) -> list[ThermalOrderWindow]:
    """
    TODO: rewrite docstring properly
    A helper function that extracts "sequence" (ie consecutive time steps) of
    similar comparative "codes" resulting from compare_planning_intraday
    It names each sequence with the type of order to be formulated

    Arguments:
    - `unit` : the thermal unit considered
    - 'delta_planning': a time series over orders_time containing -2/-1/0/1/2
      depending on the difference between the day ahead and the new planning
    - `orders_time` : an index of dates over which orders will be formulated
      (CAUTION : orders_time is assumed to be with a regular time step equal to p.time_step)
    - `p`: a named tuple of subclass Parameters_List containing the parameters

    Returns:
    list_of_delta_sequences : a list of sequences. Each sequence is a list of
    consecutive time indexes, its name reflects the bidding case among:
    - modulation_up : period where the unit is running in the two planning but new is above
    - modulation_down : period where the unit is running in the two planning but previous is above
    - extended_end : the running phase is extended at the end of the initial one
    - shortened_end : the running phase is shortened at the end of the initial one
    - extended_begin: the running phase is extended before the initial one
    - shorter_begin: the running phase is shortened before the initial one
    - new_start : the unit is now started up and then shut down during a period where it was previously always shut down
    - bridge_up : the unit is now started in between two start-up phases
    - bridge_down : a start-up phase is removed in the new planning
    - new_stop : a shut down phase is added where the unit was always started up before
    """

    # Read the previous planning in the input marker
    # previous_planning=unit.Power.GetForecast(execution_date,orders_time[0],orders_time[-1])
    previous_planning = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity
    # print "previous planning", previous_planning

    # Get the time steps for which there is a delta of program (defined as a non-zero state):
    # we create four list of indexes, to store the time indexes of each comparative code (-2,2,-1,1)
    now_up_at_t: list[DateTime] = []
    now_down_at_t: list[DateTime] = []
    modulation_up_at_t: list[DateTime] = []
    modulation_down_at_t: list[DateTime] = []

    # Sanity check if the time indexes in orders_time are separated by DeltaTime,
    # otherwise the function will not work properly
    if len(orders_time) > 2:
        for k in range(1, len(orders_time) - 1):
            if orders_time[k].add(seconds=-parameters.temporal.timestep.in_seconds()) != orders_time[k - 1]:
                cfg.logger.warning(
                    "orders_time are not with a regular time step equal to DeltaTime, the generation of orders might be impacted"
                )

    for t in orders_time:
        if delta_planning.get_value(t) == 1:
            now_up_at_t.append(t)
        elif delta_planning.get_value(t) == -1:
            now_down_at_t.append(t)
        elif delta_planning.get_value(t) == -2:
            modulation_down_at_t.append(t)
        elif delta_planning.get_value(t) == 2:
            modulation_up_at_t.append(t)

    intervals = []
    # In intervals, we will store time indexes of start and end of a sequence

    # The intervals bounds are retrieved by comparing the total minutes between to time steps:
    # if the total number of minutes is greater that p.time_step, then the time steps i
    # and i+1 correspond to bounds of two distinct intervals
    for delta_at_t in [now_up_at_t, now_down_at_t, modulation_up_at_t, modulation_down_at_t]:
        # If there is at list one time index
        if delta_at_t:
            # Store the first time index
            intervals.append(delta_at_t[0])
            # If there is at least two time indexes
            if len(delta_at_t) >= 2:
                # For each index in the list
                for i in range(len(delta_at_t) - 1):
                    # If two consecutive time indexes are not separated by DeltaTime
                    if not (delta_at_t[i + 1] - delta_at_t[i]).total_minutes() == parameters.temporal.timestep:
                        # The two are added in the intervals list
                        intervals.append(delta_at_t[i])
                        intervals.append(delta_at_t[i + 1])
                        # The last opened interval is closed with the latest time index
            intervals.append(delta_at_t[-1])

    # Intervals are generated, using the fact that by construction,
    # there is an even number of time steps in the intervals list.
    list_of_delta_sequences = []
    if intervals:
        for i in range(int(len(intervals) / 2)):
            # Start dates are even
            window_start = intervals[2 * i]
            # End dates are odd
            window_end = intervals[2 * i + 1]
            # The sequence is defined between start and end dates
            sliced_planning = delta_planning.slice(window_start, window_end)

            # CAUTION : below we assume that previous planning is defined +/- p.time_step around the orders_time
            # Read the power in the previous planning at end date of the
            # sequence + p.time_step, necessary to identify the orders to formulate
            previous_status_before = previous_planning.get_value(
                window_start.add(minutes=-parameters.temporal.timestep.in_minutes())
            ) >= equipment.minimum_power.get_value(window_start.add(minutes=-parameters.temporal.timestep.in_minutes()))

            # Read the power in the previous planning at start date of the
            # sequence - p.time_step, necessary to identify the orders to formulate
            previous_status_after = previous_planning.get_value(
                window_end.add(minutes=parameters.temporal.timestep.in_minutes())
            ) >= equipment.minimum_power.get_value(window_end.add(minutes=parameters.temporal.timestep.in_minutes()))
            # _ delta_planning = 1 or -1
            # _ previous_status_before : True or False
            # _ previous_status_after : True or False
            # ==>8 cases resulting from all the combination
            # +2 cases : modulation_up and modulation_down depending only on delta_planning (-2 or 2)
            if delta_planning.get_value(window_start) == 1 and previous_status_before:
                if previous_status_after:
                    window = ThermalOrderWindow(sliced_planning, WindowType.BRIDGE_UP)
                else:
                    window = ThermalOrderWindow(sliced_planning, WindowType.EXTENDED_END)
            elif delta_planning.get_value(window_start) == 1 and not previous_status_before:
                if previous_status_after:
                    window = ThermalOrderWindow(sliced_planning, WindowType.EXTENDED_BEGINNING)
                else:
                    window = ThermalOrderWindow(sliced_planning, WindowType.NEW_START)
            elif delta_planning.get_value(window_start) == -1 and previous_status_before:
                if previous_status_after:
                    window = ThermalOrderWindow(sliced_planning, WindowType.NEW_STOP)
                else:
                    window = ThermalOrderWindow(sliced_planning, WindowType.SHORTENED_END)
            elif delta_planning.get_value(window_start) == -1 and not previous_status_before:
                if previous_status_after:
                    window = ThermalOrderWindow(sliced_planning, WindowType.SHORTENED_BEGINNING)
                else:
                    window = ThermalOrderWindow(sliced_planning, WindowType.BRIDGE_DOWN)
            elif delta_planning.get_value(window_start) == 2:
                window = ThermalOrderWindow(sliced_planning, WindowType.MODULATION_UP)
            elif delta_planning.get_value(window_start) == -2:
                window = ThermalOrderWindow(sliced_planning, WindowType.MODULATION_DOWN)
            else:
                continue

            list_of_delta_sequences.append(window)

    return list_of_delta_sequences


class ThermalOrdersFormulator(AbstractOrdersFormulator[ThermalIDO]):
    EQUIPMENT_TYPE_NAME = "thermal"

    def formulate_equipment_orders(
        self,
        equipment: ThermalIDO,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling]]:
        orders: list[Order] = []
        couplings: list[OrderCoupling] = []

        if equipment.strategy == ThermalStrategy.INTERMEDIATE or equipment.strategy == ThermalStrategy.BASE:
            delta_planning = compare_planning(equipment, orders_timestamps, parameters)
            list_of_delta_sequences = extract_sequences_from_delta_planning(
                equipment, delta_planning, orders_timestamps, parameters
            )

            # Order creation
            compare_prices = Timeseries.from_index(
                parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0
            )

            optimization_result = equipment.id_po_for_orders.get_forecast(
                parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
            )

            cfg.logger.info(f"Formulating thermal orders for unit {equipment.name}")

            # Create the orders for each sequence.
            # NB : By construction, each sequence is a list of consecutive dates separated
            # by TimeStep with the same desired variation of planning
            for window in list_of_delta_sequences:
                cfg.logger.info(
                    f"Formulating thermal orders for unit {equipment.name} between {window.first_date()} and {window.last_date()} for case {window.window_type.value}"
                )

                number_of_indexes = len(window.index)

                # The orders are composed of flexible and inflexible orders at each time step
                # There are couplings between the flexible and inflexible orders of each time steps
                # and between the inflexible orders of different time step
                # Type of orders, type of couplings, maximal power offered and price depend on the case

                # Direction indicates if orders are coupled in increasing or decreasing
                # time steps from the first one, by default it is chronological
                direction = 1

                # parent_date indicates if the first order to create is the first or the last of the sequence, by default it is the first

                if window.window_type == WindowType.EXTENDED_END:
                    sell_or_buy = OrderType.Sell
                    parent_date = window.first_date()
                    total_start_up_cost = 0.0
                    # In this case, the inflexible part is not a single block:
                    # the last inflexible order is not coupled to the first one
                    coupling_time_step = "partial"
                    coupling_type_flexible_inflexible = CouplingType.PARENT_CHILDREN

                elif window.window_type == WindowType.SHORTENED_END:
                    sell_or_buy = OrderType.Buy
                    # In this case, the order are created from the last date of the sequence
                    # to the first to create meaningful couplings
                    parent_date = window.last_date()
                    direction = -1
                    total_start_up_cost = 0.0
                    # In this case, the inflexible part is not a single bloc:
                    # the last inflexible order is not coupled to the first one
                    coupling_time_step = "partial"
                    # In buy orders, the inflexible part excludes the flexible
                    coupling_type_flexible_inflexible = CouplingType.EXCLUSION

                elif window.window_type == WindowType.EXTENDED_BEGINNING:
                    sell_or_buy = OrderType.Sell
                    # In this case, the order are created from the last date of the sequence
                    # to the first to create meaningful couplings
                    parent_date = window.last_date()
                    direction = -1
                    total_start_up_cost = 0.0
                    # In this case, the inflexible part is not a single bloc:
                    # the last inflexible order is not coupled to the first one
                    coupling_time_step = "partial"
                    coupling_type_flexible_inflexible = CouplingType.PARENT_CHILDREN

                elif window.window_type == WindowType.SHORTENED_BEGINNING:
                    sell_or_buy = OrderType.Buy
                    parent_date = window.first_date()
                    total_start_up_cost = 0.0
                    # In this case, the inflexible part is not a single bloc:
                    # the last inflexible order is not coupled to the first one
                    coupling_time_step = "partial"
                    # In buy orders, the inflexible part excludes the flexible
                    coupling_type_flexible_inflexible = CouplingType.EXCLUSION

                elif window.window_type == WindowType.BRIDGE_UP:
                    sell_or_buy = OrderType.Sell
                    parent_date = window.first_date()
                    # A start-up cost is saved, it decreases the sell price
                    total_start_up_cost = -equipment.startup_cost.get_value(window.first_date())
                    # In this case, the inflexible part is a single bloc:
                    # the last inflexible order is coupled to the first one
                    coupling_time_step = "all"
                    coupling_type_flexible_inflexible = CouplingType.PARENT_CHILDREN

                elif window.window_type == WindowType.BRIDGE_DOWN:
                    sell_or_buy = OrderType.Buy
                    parent_date = window.first_date()
                    # A start-up cost is saved, it increases the buy price
                    total_start_up_cost = equipment.startup_cost.get_value(window.first_date())
                    # In this case, the inflexible part is a single bloc:
                    # the last inflexible order is coupled to the first one
                    coupling_time_step = "all"
                    # In buy orders, the inflexible part excludes the flexible
                    coupling_type_flexible_inflexible = CouplingType.EXCLUSION

                elif window.window_type == WindowType.NEW_STOP:
                    sell_or_buy = OrderType.Buy
                    parent_date = window.first_date()
                    # A start-up cost is added, it decreases the buy price
                    total_start_up_cost = -equipment.startup_cost.get_value(window.first_date())
                    # In this case, the inflexible part is a single bloc:
                    # the last inflexible order is coupled to the first one
                    coupling_time_step = "all"
                    # In buy orders, the inflexible part excludes the flexible
                    coupling_type_flexible_inflexible = CouplingType.EXCLUSION

                elif window.window_type == WindowType.NEW_START:
                    sell_or_buy = OrderType.Sell
                    parent_date = window.first_date()
                    # A start-up cost is added, it increases the sell price
                    total_start_up_cost = equipment.startup_cost.get_value(window.first_date())
                    # In this case, the inflexible part is a single bloc:
                    # the last inflexible order is coupled to the first one
                    coupling_time_step = "all"
                    coupling_type_flexible_inflexible = CouplingType.PARENT_CHILDREN

                elif window.window_type == WindowType.MODULATION_UP:
                    sell_or_buy = OrderType.Sell
                    parent_date = window.first_date()
                    direction = 1
                    total_start_up_cost = 0.0
                    # In this case, orders are independent and fully flexible
                    coupling_time_step = "none"
                    coupling_type_flexible_inflexible = None

                elif window.window_type == WindowType.MODULATION_DOWN:
                    sell_or_buy = OrderType.Buy
                    parent_date = window.first_date()
                    direction = 1
                    total_start_up_cost = 0.0
                    # In this case, orders are independent and fully flexible
                    coupling_time_step = "none"
                    coupling_type_flexible_inflexible = None

                else:
                    cfg.logger.warning(
                        f"Unrecognised name of sequence : {window.window_type.value}, for unit {equipment.name} between {window.first_date()} and {window.last_date()}"
                    )
                    continue

                # Collect inflexible bids to build timestep couplings after the loop
                inflexible_bids: list[tuple[DateTime, Order]] = []

                # Calculate the quantity of power over which to distribute the start-up cost
                q = 0.0
                start_up_wost_per_mw = 0.0
                if total_start_up_cost != 0.0:
                    # For buy orders the startup cost is spread over the inflexible blocks equal to previous P
                    if sell_or_buy == OrderType.Buy:
                        for t in window.index:
                            # TODO: check with POs that start and end forecast dates are proper
                            q += equipment.id_po_for_orders.get_forecast(
                                parameters.temporal.execution_date, window.first_date(), window.last_date()
                            ).get_value(t)

                    # For sell orders the startup cost is spread over the inflexible blocks equal to Pmin
                    else:
                        for t in window.index:
                            q += equipment.minimum_power.get_value(t)

                    if q == 0.0 and sell_or_buy == OrderType.Sell:
                        cfg.logger.warning(
                            f"Null Pmin for unit {equipment.name}. Start up cost is either null or neglected."
                        )
                        # In the case of Pmin=0, we neglect StartUpCost and avoid division by 0
                        start_up_wost_per_mw = 0.0

                    # Happens if previous power is null in a buy order but ClearedQuantity is not
                    if q == 0 and sell_or_buy == OrderType.Buy:
                        p_min = 0.0
                        for t in window.index:
                            p_min += equipment.minimum_power.get_value(t)
                        if p_min == 0:
                            cfg.logger.warning(
                                f"Null Pmin for unit {equipment.name}. Start up cost is either null or neglected."
                            )
                            # In the case of Pmin=0, we neglect StartUpCost and avoid division by 0
                            start_up_wost_per_mw = 0.0
                        else:
                            # We make a conservative hypothesis for start-up cost affectation
                            start_up_wost_per_mw = total_start_up_cost / p_min

                    else:
                        start_up_wost_per_mw = total_start_up_cost / q

                # Loop over the time Steps to create the orders.
                t = parent_date.add(minutes=-parameters.temporal.timestep.in_minutes() * direction)

                for _ in range(0, number_of_indexes):
                    # For i=0, t=ParentDate. Then we go backward or downward depending on the "Direction"
                    t = t.add(minutes=parameters.temporal.timestep.in_minutes() * direction)

                    # Read the latest planning in the input Marker
                    p_plan = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity
                    previous_p = p_plan.get_value(t)

                    # Read the new optimal planning resulting from the optimization
                    new_p = optimization_result.get_value(t)

                    # The volume offered depend on the case
                    if window.window_type == WindowType.MODULATION_UP:
                        # In modulation case, we offer the delta between the two programs
                        q_max_flexible = new_p - previous_p
                        # There is no inflexible part
                        q_inflexible = 0.0
                        sell_submitted_volume.sum_value_at(t, q_max_flexible)

                    elif window.window_type == WindowType.MODULATION_DOWN:
                        # In modulation case, we offer the delta between the two programs
                        q_max_flexible = previous_p - new_p
                        # There is no inflexible part
                        q_inflexible = 0.0
                        buy_submitted_volume.sum_value_at(t, q_max_flexible)

                    elif sell_or_buy == OrderType.Sell:
                        # In this case previous_p < Pmin by construction but could be >0
                        # in case of a start-up/start down phase, thus it is subtracted to Pmin
                        # In other sell orders, flexible offer between new power and Pmin.
                        q_max_flexible = new_p - equipment.minimum_power.get_value(t)
                        # Inflexible order at Pmin.
                        q_inflexible = equipment.minimum_power.get_value(t) - previous_p
                        sell_submitted_volume.sum_value_at(t, q_max_flexible + q_inflexible)

                    else:
                        # by construction, previous_p - unit.MinimumPower.GetValue(t) >= 0
                        # In buy orders, flexible offer between previous power and Pmin
                        q_max_flexible = previous_p - equipment.minimum_power.get_value(t)
                        # Inflexible order at previous power
                        q_inflexible = previous_p
                        # Inflexible and flexible orders are EXCLUSION-coupled,
                        # so maximum buy submitted volume is the biggest
                        buy_submitted_volume.sum_value_at(t, q_inflexible)

                        # TODO: check sign
                    # In Intraday market, the unit submit order either because it hopes
                    # to be competitive or to cover its imbalances:
                    # - In the first case, the offered price is its marginal cost (+ or - start up cost in some cases)
                    # - In the latter case, the marginal cost must be decreased from
                    #   the estimation of the Imbalance Settlement Price
                    # - In sell orders : if RE price is high, unit is willing to sell power
                    #   even at a low price to avoid a significant penalty
                    # - In buy orders : if RE price is low, unit is willing to buy below its
                    #   Marginal cost to avoid to lose between its marginal cost and the RE

                    if q_max_flexible > parameters.allowed_round_off_error:
                        order_name = f"ID_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}_{equipment.name}_{t.format('YYYY_MM_DD_HH_mm_ss')}_flexible_{window.window_type.value}"
                        bid_output = build_intraday_order(
                            equipment,
                            order_name,
                            equipment.variable_cost.get_value(t) - compare_prices.get_value(t),
                            0.0,
                            q_max_flexible,
                            sell_or_buy,
                            t,
                            parameters,
                        )
                        orders.append(bid_output)

                        # Store the flexible part to be coupled with the inflexible part
                        bid_flexible = bid_output

                    # If Pmin>0 a second order -inflexible- is created to buy up to
                    # the whole Power (in the flexible part, it is limited by the Pmin)
                    if q_inflexible > parameters.allowed_round_off_error:
                        order_name = f"ID_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}_{equipment.name}_{t.format('YYYY_MM_DD_HH_mm_ss')}_inflexible_{window.window_type.value}"
                        bid_output = build_intraday_order(
                            equipment,
                            order_name,
                            equipment.variable_cost.get_value(t) + start_up_wost_per_mw - compare_prices.get_value(t),
                            q_inflexible,
                            q_inflexible,
                            sell_or_buy,
                            t,
                            parameters,
                        )
                        orders.append(bid_output)

                        inflexible_bids.append((t, bid_output))

                        # The inflexible order is coupled with the flexible part if it exists
                        if q_max_flexible > parameters.allowed_round_off_error:
                            couplings.append(
                                OrderCoupling(
                                    name=f"{coupling_type_flexible_inflexible}_ID_{equipment.name}_{t.format('YYYY_MM_DD_HH_mm_ss')}_{window.window_type.value}_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}",
                                    coupling_type=coupling_type_flexible_inflexible,
                                    orders=[bid_output, bid_flexible],
                                )
                            )

                    # Sanity check
                    elif window.window_type not in [WindowType.MODULATION_UP, WindowType.MODULATION_DOWN]:
                        cfg.logger.warning(
                            f"Unrecognised name of sequence : {window.window_type.value}, for unit {equipment.name} between {window.first_date()} and {window.last_date()}"
                        )

                # Create PARENT_CHILDREN chain couplings across timesteps now that all inflexible bids are known
                if number_of_indexes > 1 and coupling_time_step != "none" and len(inflexible_bids) > 1:
                    for k in range(len(inflexible_bids) - 1):
                        ts, bid = inflexible_bids[k]
                        _, next_bid = inflexible_bids[k + 1]
                        couplings.append(
                            OrderCoupling(
                                name=f"PAR_CHIL_ID_{equipment.name}_{ts.format('YYYY_MM_DD_HH_mm_ss')}_{window.window_type.value}_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}",
                                coupling_type=CouplingType.PARENT_CHILDREN,
                                orders=[bid, next_bid],
                            )
                        )
                    if coupling_time_step == "all":
                        ts, bid = inflexible_bids[-1]
                        couplings.append(
                            OrderCoupling(
                                name=f"PAR_CHIL_ID_{equipment.name}_{ts.format('YYYY_MM_DD_HH_mm_ss')}_{window.window_type.value}_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}",
                                coupling_type=CouplingType.PARENT_CHILDREN,
                                orders=[bid, inflexible_bids[0][1]],
                            )
                        )

        elif equipment.strategy == ThermalStrategy.PEAK:
            previous_power = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity

            for t in orders_timestamps:
                minimum_power = equipment.minimum_power.get_value(t)
                maximum_power = equipment.maximum_power.get_value(t)

                if maximum_power == 0.0 or maximum_power < minimum_power:
                    cfg.logger.warning(
                        f"Maximum power of unit {equipment.name} is null or lower than minimum power at time {str(t)}. No order will therefore be created."
                    )
                    continue

                generate_inflexible_order = minimum_power > 0

                if previous_power is None:
                    pow_t = 0.0
                else:
                    pow_t = previous_power.get_value(t)

                if generate_inflexible_order and pow_t == 0.0:
                    # Compute the price
                    min_hours_on = 0.0  # FIXME: is 0.0 a good default value?
                    if equipment.minimum_time_on is not None:
                        min_hours_on = (
                            1.0 if equipment.minimum_time_on.in_hours() == 0.0 else equipment.minimum_time_on.in_hours()
                        )
                    q = minimum_power * min_hours_on
                    price = equipment.startup_cost.get_value(t) / q + equipment.variable_cost.get_value(t)

                    # Create the inflex order instance
                    inflexible_bid_name = (
                        f"ID_inflexible_order_Sell_at_{t.format('YYYY_MM_DD_HH_mm_ss')}_for_unit_{equipment.name}"
                    )
                    inflexible_bid_output = build_intraday_order(
                        equipment,
                        inflexible_bid_name,
                        price,
                        minimum_power,
                        minimum_power,
                        OrderType.Sell,
                        t,
                        parameters,
                    )
                    orders.append(inflexible_bid_output)

                    sell_submitted_volume.sum_value_at(t, minimum_power)

                    q_max = maximum_power - minimum_power
                    if q_max > parameters.allowed_round_off_error:
                        flexible_bid_name = (
                            f"ID_flexible_order_Sell_at_{t.format('YYYY_MM_DD_HH_mm_ss')}_for_unit_{equipment.name}"
                        )
                        flexible_bid_output = build_intraday_order(
                            equipment,
                            flexible_bid_name,
                            equipment.variable_cost.get_value(t),
                            0.0,
                            q_max,
                            OrderType.Sell,
                            t,
                            parameters,
                        )
                        orders.append(flexible_bid_output)
                        sell_submitted_volume.sum_value_at(t, q_max)

                        couplings.append(
                            OrderCoupling(
                                name=f"PARENT_CHILDREN_ID_inflexible_flexible_orders_Sell_at_{t.format('YYYY_MM_DD_HH_mm_ss')}_for_unit_{equipment.name}",
                                coupling_type=CouplingType.PARENT_CHILDREN,
                                orders=[inflexible_bid_output, flexible_bid_output],
                            )
                        )
                else:
                    q_max = maximum_power - pow_t

                    if q_max > parameters.allowed_round_off_error:
                        flexible_bid_name = (
                            f"ID_flexible_order_Sell_at_{t.format('YYYY_MM_DD_HH_mm_ss')}_for_unit_{equipment.name}"
                        )
                        flexible_bid_output = build_intraday_order(
                            equipment,
                            flexible_bid_name,
                            equipment.variable_cost.get_value(t),
                            0.0,
                            q_max,
                            OrderType.Sell,
                            t,
                            parameters,
                        )
                        orders.append(flexible_bid_output)
                        sell_submitted_volume.sum_value_at(t, q_max)

                if pow_t != 0.0 and pow_t != minimum_power:
                    q_max = pow_t - minimum_power
                    if q_max > parameters.allowed_round_off_error:
                        flexible_bid_name = (
                            f"ID_flexible_order_Buy_at_{t.format('YYYY_MM_DD_HH_mm_ss')}_for_unit_{equipment.name}"
                        )
                        flexible_bid_output = build_intraday_order(
                            equipment,
                            flexible_bid_name,
                            equipment.variable_cost.get_value(t),
                            0.0,
                            q_max,
                            OrderType.Buy,
                            t,
                            parameters,
                        )
                        orders.append(flexible_bid_output)
                        buy_submitted_volume.sum_value_at(t, q_max)

        return orders, couplings
