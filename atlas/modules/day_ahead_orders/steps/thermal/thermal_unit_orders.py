"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import cast

import pendulum
from pendulum import DateTime, Duration

import atlas.config as cfg
from atlas.enums import ThermalOrderState
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.timeseries import Timeseries
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.order_factory import ThermalCouplingFactory, ThermalOrderFactory
from atlas.timing import generate_datetimes


@dataclass
class ThermalTimeFrames:
    """
    Time frame partitions derived from a thermal unit's state sequence.

    :param flexible: Timesteps where the unit is in stable ON state, used for flexible and reserve orders.
    :param startup: Timesteps covering the startup ramp window (one step longer than the ramp, clipped to the sim window).
    :param shutdown: Timesteps covering the shutdown ramp window (shifted back one step, null-power step excluded).
    :param inflexible: All online timesteps, used for inflexible (Pmin) orders.
    :param K_start: Number of STARTUP-state timesteps within the simulation window.
    :param K_stop: Number of SHUTDOWN-state timesteps within the simulation window.
    :param startup_ends_here: True when the startup ramp completes within the simulation window (STARTUP→ON transition visible).
    :param shutdown_starts_here: True when the shutdown ramp begins within the simulation window (ON→SHUTDOWN transition visible).
    """

    flexible: list[DateTime]
    startup: list[DateTime]
    shutdown: list[DateTime]
    inflexible: list[datetime]
    K_start: int
    K_stop: int
    startup_ends_here: bool
    shutdown_starts_here: bool


def _compute_time_frames(
    online_timeframe: Timeseries,
    orders_time: list[DateTime],
    step: Duration,
) -> ThermalTimeFrames:
    """
    Partition the simulation window into flexible, startup, shutdown and inflexible time frames.

    :param online_timeframe: State-encoded timeseries (:class:`~atlas.enums.ThermalOrderState` values).
    :param orders_time: Ordered list of simulation timesteps.
    :param step: Simulation timestep duration.
    :return: Populated :class:`ThermalTimeFrames`.

    Example::

        tf = _compute_time_frames(online_ts, orders_time, step)
        # tf.flexible  → stable ON timesteps
        # tf.startup   → startup ramp window
        # tf.shutdown  → shutdown ramp window
        # tf.K_start   → ramp steps visible in window
    """
    online_values = online_timeframe.values
    online_index = online_timeframe.index

    # Detect startup completion (STARTUP→ON) and shutdown initiation (ON→SHUTDOWN)
    startup_ends_here = False
    shutdown_starts_here = False
    _startup_to_on = ThermalOrderState.STARTUP - ThermalOrderState.ON
    _on_to_shutdown = ThermalOrderState.SHUTDOWN - ThermalOrderState.ON
    for a, b in zip(online_values[:-1], online_values[1:], strict=False):
        if b - a == _on_to_shutdown:
            shutdown_starts_here = True
        if a - b == _startup_to_on:
            startup_ends_here = True
        if startup_ends_here and shutdown_starts_here:
            break

    # Count ramp timesteps and locate the first ramp timestep within the window
    online_index_set = set(online_index)
    orders_time_set = set(orders_time)
    K_start = K_stop = 0
    begin_startup: DateTime | None = None
    begin_shutdown: DateTime | None = None
    flexible: list[DateTime] = []

    for t in orders_time:
        if t not in online_index_set:
            continue
        v = online_timeframe.get_value(t)
        if v == ThermalOrderState.ON:
            flexible.append(t)
        elif v == ThermalOrderState.STARTUP:
            K_start += 1
            if begin_startup is None:
                begin_startup = t
        elif v == ThermalOrderState.SHUTDOWN:
            K_stop += 1
            if begin_shutdown is None:
                begin_shutdown = t

    # Startup ramp window: one step longer than K_start, clipped to sim window
    startup: list[DateTime] = []
    startup_set: set[DateTime] = set()
    if K_start > 0:
        assert begin_startup is not None
        startup = [
            t for t in generate_datetimes(begin_startup, begin_startup + K_start * step, step) if t in orders_time_set
        ]
        startup_set = set(startup)

    # Shutdown ramp window: shifted back one step (last stable Pmin step included), last null-power step excluded
    shutdown: list[DateTime] = []
    shutdown_set: set[DateTime] = set()
    if K_stop > 0:
        assert begin_shutdown is not None
        shutdown = [
            t
            for t in generate_datetimes(begin_shutdown - step, begin_shutdown + (K_stop - 1) * step, step)
            if t in orders_time_set
        ]
        shutdown_set = set(shutdown)

    # Remove startup/shutdown overlaps from flexible (boundary Pmin steps belong to ramp windows)
    if startup_set or shutdown_set:
        flexible = [t for t in flexible if t not in startup_set and t not in shutdown_set]

    # Corner case: unit online for exactly one step → singleton overlap → drop from shutdown
    if K_start > 0 and K_stop > 0:
        overlap = startup_set & shutdown_set
        if len(overlap) == 1:
            shutdown = [t for t in shutdown if t not in overlap]

    return ThermalTimeFrames(
        flexible=flexible,
        startup=startup,
        shutdown=shutdown,
        inflexible=online_index,
        K_start=K_start,
        K_stop=K_stop,
        startup_ends_here=startup_ends_here,
        shutdown_starts_here=shutdown_starts_here,
    )


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
        # Cache index/values once: each access on Timeseries rebuilds a Python list from polars.
        online_values = online_timeframe.values
        if ThermalOrderState.OFF in online_values:
            cfg.logger.debug(f"Unit {unit.name} is offline. No orders have been formulated for this unit")
            return orders, couplings

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

        T_start = int(math.floor(unit.startup_duration / step))
        T_stop = int(math.floor(unit.shutdown_duration / step))
        q_min = unit.minimum_power.max()

        if isinstance(unit.minimum_power, LazyTimeseries):
            min_power = unit.minimum_power.collect()
        else:
            min_power = cast(Timeseries, unit.minimum_power)
        null_minimum_power = min_power.filter(self.orders_time, inplace=False).min() == 0

        has_startup = ThermalOrderState.STARTUP in online_values

        tf = _compute_time_frames(online_timeframe, self.orders_time, step)

        q_max_ts = (
            unit.maximum_power.filter(tf.flexible, inplace=False)
            - unit.minimum_power.filter(tf.flexible, inplace=False)
            - manual_reserves_down_procured.filter(tf.flexible, inplace=False)
            - manual_reserves_up_procured.filter(tf.flexible, inplace=False)
            - automated_reserves_down_procured.filter(tf.flexible, inplace=False)
            - automated_reserves_up_procured.filter(tf.flexible, inplace=False)
        )

        prop_pen = 1 - self.parameters.proportional_reserves_penalty
        auto_pen = self.parameters.automated_unprocured_reserves_penalty
        manual_unprocured_reserves_penalty = self.parameters.manual_unprocured_reserves_penalty

        # ------------------------------------------------------- #
        #                                                         #
        #                   Flexible layer                        #
        #                                                         #
        # ------------------------------------------------------- #
        # Precompute filtered values aligned with flexible_time_frame to avoid per-step Timeseries.get_value calls.
        flex_qmax = q_max_ts.values
        flex_vc = unit.variable_cost.filter(tf.flexible, inplace=False).values
        flex_auto_dn = automated_reserves_down_procured.filter(tf.flexible, inplace=False).values
        flex_man_dn = manual_reserves_down_procured.filter(tf.flexible, inplace=False).values
        flex_auto_up = automated_reserves_up_procured.filter(tf.flexible, inplace=False).values
        flex_man_up = manual_reserves_up_procured.filter(tf.flexible, inplace=False).values

        for t, q_max, variable_cost, auto_dn, man_dn, auto_up, man_up in zip(
            tf.flexible, flex_qmax, flex_vc, flex_auto_dn, flex_man_dn, flex_auto_up, flex_man_up, strict=True
        ):
            formatted_t = t.format("DD_MM_YYYY_HH_mm_ss")

            # Part 1: flexible order
            if q_max <= 0.0:
                cfg.logger.warning(
                    f"Negative or null amount of energy in the flexible order to be offered by unit {unit.name} at time {str(t)}. "
                    "The order will therefore not be created."
                )
            else:
                orders.append(
                    ThermalOrderFactory.flexible(unit, q_max, variable_cost, t, step, ed, formatted_t, scenario_suffix)
                )

            # Part 2: reserve requirement orders
            if auto_dn > 0.0:
                orders.append(
                    ThermalOrderFactory.reserve(
                        unit,
                        auto_dn,
                        variable_cost,
                        auto_pen,
                        "downward",
                        "automated",
                        prop_pen,
                        t,
                        step,
                        ed,
                        formatted_t,
                        scenario_suffix,
                    )
                )
            if man_dn > 0.0:
                orders.append(
                    ThermalOrderFactory.reserve(
                        unit,
                        man_dn,
                        variable_cost,
                        manual_unprocured_reserves_penalty,
                        "downward",
                        "manual",
                        prop_pen,
                        t,
                        step,
                        ed,
                        formatted_t,
                        scenario_suffix,
                    )
                )
            if auto_up > 0.0:
                orders.append(
                    ThermalOrderFactory.reserve(
                        unit,
                        auto_up,
                        variable_cost,
                        auto_pen,
                        "upward",
                        "automated",
                        prop_pen,
                        t,
                        step,
                        ed,
                        formatted_t,
                        scenario_suffix,
                    )
                )
            if man_up > 0.0:
                orders.append(
                    ThermalOrderFactory.reserve(
                        unit,
                        man_up,
                        variable_cost,
                        manual_unprocured_reserves_penalty,
                        "upward",
                        "manual",
                        prop_pen,
                        t,
                        step,
                        ed,
                        formatted_t,
                        scenario_suffix,
                    )
                )

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
            if tf.K_start > 0:
                for t, i in zip(tf.startup, range(tf.K_start + 1), strict=False):
                    q_sell = (
                        round((T_start - tf.K_start + i) * q_step_up) if tf.startup_ends_here else round(i * q_step_up)
                    )
                    bid_output = ThermalOrderFactory.startup_ramp(unit, q_sell, t, step, ed, scenario_suffix)
                    orders.append(bid_output)
                    inflexible_orders.append(bid_output)
                    Q += q_sell

            # Part 2: Shutdown orders
            # Does not create bids if there is not at least one stable state within the online sequence (prevents creating
            # shutdown ramps without the starting point at Pmin within the simulation timeframe for border case reasons.
            if tf.K_stop > 0:
                for t, i in zip(tf.shutdown, range(tf.K_stop + 1), strict=False):
                    q_sell = (
                        round((T_stop - i) * q_step_down)
                        if tf.shutdown_starts_here
                        else round(q_min - (T_stop - tf.K_stop + i) * q_step_down)
                    )
                    bid_output = ThermalOrderFactory.shutdown_ramp(unit, q_sell, t, step, ed, scenario_suffix)
                    orders.append(bid_output)
                    inflexible_orders.append(bid_output)
                    Q += q_sell

            # Part 3: inflexible orders at Pmin
            # Build a name->order index once to look up flexible bids in O(1) instead of O(N) per check.
            orders_by_name: dict[str, OrderDAO] = {bid.name: bid for bid in orders}
            flexible_types = (
                "flexible_order",
                "manual_upward_reserve_order",
                "automated_upward_reserve_order",
                "manual_downward_reserve_order",
                "automated_downward_reserve_order",
            )
            for t_raw in tf.inflexible:
                t = pendulum.instance(t_raw)
                formatted_t = t.format("DD_MM_YYYY_HH_mm_ss")
                min_p = unit.minimum_power.get_value(t)
                variable_cost = unit.variable_cost.get_value(t)
                bid_output = ThermalOrderFactory.inflexible(unit, min_p, variable_cost, t, step, ed, formatted_t, case)
                orders.append(bid_output)
                inflexible_orders.append(bid_output)
                Q += min_p

                # Link inflexible to each existing flexible child at the same timestep
                config_bid_name = f"_at_{formatted_t}_for_unit_{unit.name}{scenario_suffix}"
                for flex_type in flexible_types:
                    flexible_bid = orders_by_name.get(flex_type + config_bid_name)
                    if flexible_bid is not None:
                        couplings.append(
                            ThermalCouplingFactory.parent_children(
                                bid_output, flexible_bid, unit.name, formatted_t, scenario_suffix
                            )
                        )

            # Part 4: identical_ratio link between all inflexible orders
            date = pendulum.DateTime.instance(tf.inflexible[0])
            couplings.append(
                ThermalCouplingFactory.identical_ratio(
                    inflexible_orders, unit.name, date.format("DD_MM_YYYY_HH_mm_ss"), scenario_suffix
                )
            )

            # Part 5 : if startup, amortise startup cost on all inflexible layer
            amortized_cost = round(unit.startup_cost.get_value(t) / Q, 2)
            for order in inflexible_orders:
                # Add the spreading of start up cost only if the startup is complete within the sequence
                if has_startup and tf.startup_ends_here:
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
