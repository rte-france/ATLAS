"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from dataclasses import dataclass

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import CouplingType, OrderType, ThermalStrategy
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.input_objects.thermal import ThermalIDO
from atlas.modules.intraday_orders.models.enums import InflexibleChaining, PlanningDelta, WindowType
from atlas.modules.intraday_orders.models.thermal_order_window import ThermalOrderWindow
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order, engaged_quantity
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


@dataclass(frozen=True)
class _WindowConfig:
    order_type: OrderType
    parent_is_first: bool  # True = iterate forward from first date, False = backward from last date
    startup_cost_sign: int  # 0 = none, +1 = cost is added (raises price), -1 = cost is saved (lowers price)
    chaining: InflexibleChaining
    flex_inflex_coupling: CouplingType | None  # None only for MODULATION (no inflexible block)


# Maps each WindowType to its bidding configuration.
# Reading this table answers: for this situation, do we sell or buy, from which end of
# the window, and how are startup costs and inflexible blocks chained together?
_WINDOW_CONFIGS: dict[WindowType, _WindowConfig] = {
    #                                order_type     parent_is_first  startup_cost_sign  chaining                   flex_inflex_coupling
    WindowType.EXTENDED_END: _WindowConfig(
        OrderType.Sell, True, 0, InflexibleChaining.CHAIN, CouplingType.PARENT_CHILDREN
    ),
    WindowType.SHORTENED_END: _WindowConfig(OrderType.Buy, False, 0, InflexibleChaining.CHAIN, CouplingType.EXCLUSION),
    WindowType.EXTENDED_BEGINNING: _WindowConfig(
        OrderType.Sell, False, 0, InflexibleChaining.CHAIN, CouplingType.PARENT_CHILDREN
    ),
    WindowType.SHORTENED_BEGINNING: _WindowConfig(
        OrderType.Buy, True, 0, InflexibleChaining.CHAIN, CouplingType.EXCLUSION
    ),
    WindowType.BRIDGE_UP: _WindowConfig(
        OrderType.Sell, True, -1, InflexibleChaining.RING, CouplingType.PARENT_CHILDREN
    ),
    WindowType.BRIDGE_DOWN: _WindowConfig(OrderType.Buy, True, +1, InflexibleChaining.RING, CouplingType.EXCLUSION),
    WindowType.NEW_STOP: _WindowConfig(OrderType.Buy, True, -1, InflexibleChaining.RING, CouplingType.EXCLUSION),
    WindowType.NEW_START: _WindowConfig(
        OrderType.Sell, True, +1, InflexibleChaining.RING, CouplingType.PARENT_CHILDREN
    ),
    WindowType.MODULATION_UP: _WindowConfig(OrderType.Sell, True, 0, InflexibleChaining.NONE, None),
    WindowType.MODULATION_DOWN: _WindowConfig(OrderType.Buy, True, 0, InflexibleChaining.NONE, None),
}


def compute_planning_delta(
    equipment: ThermalIDO, orders_timestamps: list[DateTime], parameters: IntradayOrdersParameters
) -> Timeseries:
    """Compare the cleared engagement (DA + prior ID sessions) to the new intraday planning.

    Returns a timeseries of :class:`PlanningDelta` codes indicating, per timestep, whether
    the unit needs to start up, shut down, modulate up/down, or stay put.

    :param equipment: Thermal unit to evaluate.
    :param orders_timestamps: Timestamps for which orders will be formulated.
    :param parameters: Intraday orders parameters.
    :return: Timeseries of integer PlanningDelta codes over the order window.
    """
    cleared_engagement = engaged_quantity(equipment, parameters)
    target_planning = equipment.id_po_for_orders.get_forecast(
        parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
    )

    planning_delta = Timeseries.from_index(
        parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0.0
    )
    for t in orders_timestamps:
        cleared_power = cleared_engagement.get_value(t)
        target_power = target_planning.get_value(t)
        pmin = equipment.minimum_power.get_value(t)

        if target_power > cleared_power:
            if cleared_power >= pmin:
                code = PlanningDelta.MODULATION_UP
            elif target_power >= pmin:
                code = PlanningDelta.STARTUP
            else:
                code = PlanningDelta.NO_CHANGE
        elif target_power < cleared_power:
            if target_power >= pmin:
                code = PlanningDelta.MODULATION_DOWN
            elif cleared_power >= pmin:
                code = PlanningDelta.SHUTDOWN
            else:
                code = PlanningDelta.NO_CHANGE
        else:
            code = PlanningDelta.NO_CHANGE

        planning_delta.set_value(t, code)

    return planning_delta


def build_order_windows(
    equipment: ThermalIDO, planning_delta: Timeseries, orders_time: list[DateTime], parameters: IntradayOrdersParameters
) -> list[ThermalOrderWindow]:
    """Group consecutive timesteps sharing the same PlanningDelta code into labelled order windows.

    Each window is classified (NEW_START, BRIDGE_UP, EXTENDED_END, etc.) based on the delta code
    and whether the unit was running immediately before and after the window in the cleared engagement.
    This classification drives the order type and coupling strategy in the formulation step.

    :param equipment: Thermal unit being processed.
    :param planning_delta: Timeseries of PlanningDelta codes from :func:`compute_planning_delta`.
    :param orders_time: Ordered list of timestamps spanning the order window.
    :param parameters: Intraday orders parameters.
    :return: List of classified ThermalOrderWindows ready for order formulation.
    """
    cleared_engagement = engaged_quantity(equipment, parameters)

    if len(orders_time) > 2:
        for k in range(1, len(orders_time) - 1):
            if orders_time[k].add(seconds=-parameters.temporal.timestep.in_seconds()) != orders_time[k - 1]:
                cfg.logger.warning(
                    "orders_time are not with a regular time step equal to DeltaTime, the generation of orders might be impacted"
                )

    startup_at: list[DateTime] = []
    shutdown_at: list[DateTime] = []
    modulation_up_at: list[DateTime] = []
    modulation_down_at: list[DateTime] = []

    for t in orders_time:
        code = PlanningDelta(int(planning_delta.get_value(t)))
        if code == PlanningDelta.STARTUP:
            startup_at.append(t)
        elif code == PlanningDelta.SHUTDOWN:
            shutdown_at.append(t)
        elif code == PlanningDelta.MODULATION_UP:
            modulation_up_at.append(t)
        elif code == PlanningDelta.MODULATION_DOWN:
            modulation_down_at.append(t)

    # A window is a maximal run of consecutive timesteps sharing the same delta code.
    # Split each code's timestamps wherever a gap (more than one timestep) breaks the run.
    step_minutes = parameters.temporal.timestep.in_minutes()

    def split_into_runs(timestamps: list[DateTime]) -> list[tuple[DateTime, DateTime]]:
        runs: list[tuple[DateTime, DateTime]] = []
        if not timestamps:
            return runs
        run_start = timestamps[0]
        for previous, current in zip(timestamps, timestamps[1:], strict=False):
            if (current - previous).total_minutes() != step_minutes:
                runs.append((run_start, previous))
                run_start = current
        runs.append((run_start, timestamps[-1]))
        return runs

    windows: list[tuple[DateTime, DateTime]] = []
    for delta_at_t in (startup_at, shutdown_at, modulation_up_at, modulation_down_at):
        windows.extend(split_into_runs(delta_at_t))

    order_windows: list[ThermalOrderWindow] = []
    for window_start, window_end in windows:
        sliced_delta = planning_delta.slice(window_start, window_end)

        # Whether the unit was running in the *previous* planning just before/after this window
        # determines whether we are extending an existing run, bridging a gap, or starting fresh.
        t_before = window_start.add(minutes=-parameters.temporal.timestep.in_minutes())
        t_after = window_end.add(minutes=parameters.temporal.timestep.in_minutes())
        was_running_before = t_before in cleared_engagement and cleared_engagement.get_value(
            t_before
        ) >= equipment.minimum_power.get_value(t_before)
        is_running_after = t_after in cleared_engagement and cleared_engagement.get_value(
            t_after
        ) >= equipment.minimum_power.get_value(t_after)

        code = PlanningDelta(int(planning_delta.get_value(window_start)))
        if code == PlanningDelta.STARTUP and was_running_before:
            window_type = WindowType.BRIDGE_UP if is_running_after else WindowType.EXTENDED_END
        elif code == PlanningDelta.STARTUP and not was_running_before:
            window_type = WindowType.EXTENDED_BEGINNING if is_running_after else WindowType.NEW_START
        elif code == PlanningDelta.SHUTDOWN and was_running_before:
            window_type = WindowType.NEW_STOP if is_running_after else WindowType.SHORTENED_END
        elif code == PlanningDelta.SHUTDOWN and not was_running_before:
            window_type = WindowType.SHORTENED_BEGINNING if is_running_after else WindowType.BRIDGE_DOWN
        elif code == PlanningDelta.MODULATION_UP:
            window_type = WindowType.MODULATION_UP
        elif code == PlanningDelta.MODULATION_DOWN:
            window_type = WindowType.MODULATION_DOWN
        else:
            continue

        order_windows.append(ThermalOrderWindow(sliced_delta, window_type))

    return order_windows


class ThermalOrdersFormulator(AbstractOrdersFormulator[ThermalIDO]):
    EQUIPMENT_TYPE_NAME = "thermal"

    def formulate_equipment_orders(
        self,
        equipment: ThermalIDO,
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling], Timeseries, Timeseries]:
        if equipment.strategy in (ThermalStrategy.BASE, ThermalStrategy.INTERMEDIATE):
            orders, couplings, sell_values, buy_values = self._formulate_base_intermediate(
                equipment, orders_timestamps, parameters
            )
        elif equipment.strategy == ThermalStrategy.PEAK:
            orders, couplings, sell_values, buy_values = self._formulate_peak(equipment, orders_timestamps, parameters)
        else:
            zero = Timeseries.from_index(
                parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0.0
            )
            return [], [], zero, zero
        sell_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, sell_values
        )
        buy_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, buy_values
        )
        return orders, couplings, sell_submitted_volume, buy_submitted_volume

    def _formulate_base_intermediate(
        self,
        equipment: ThermalIDO,
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling], list[float], list[float]]:
        """Formulate orders for BASE and INTERMEDIATE thermal units.

        Strategy: compare the new ID planning to the cleared engagement, identify windows of
        change (startup/shutdown/modulation), then emit paired flexible+inflexible sell/buy orders
        with appropriate couplings to express the unit's commitment structure to the market.
        """
        orders: list[Order] = []
        couplings: list[OrderCoupling] = []
        sell_values: list[float] = [0.0] * len(orders_timestamps)
        buy_values: list[float] = [0.0] * len(orders_timestamps)
        t_to_idx: dict = {t: i for i, t in enumerate(orders_timestamps)}

        planning_delta = compute_planning_delta(equipment, orders_timestamps, parameters)
        order_windows = build_order_windows(equipment, planning_delta, orders_timestamps, parameters)

        cleared_engagement = engaged_quantity(equipment, parameters)
        target_planning = equipment.id_po_for_orders.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
        )

        for window in order_windows:
            cfg.logger.info(
                f"Formulating thermal orders for unit {equipment.name} between {window.first_date()} and {window.last_date()} for case {window.window_type.value}"
            )

            config = _WINDOW_CONFIGS[window.window_type]
            number_of_indexes = len(window.index)
            is_modulation = config.chaining == InflexibleChaining.NONE
            direction = 1 if config.parent_is_first else -1
            parent_date = window.first_date() if config.parent_is_first else window.last_date()

            # Startup cost amortised per MW over the inflexible blocks of this window.
            # Sell windows: spread over Pmin (the committed minimum output).
            # Buy windows: spread over the target planning power (the capacity being re-acquired).
            startup_cost_per_mw = 0.0
            if config.startup_cost_sign != 0:
                total_startup_cost = config.startup_cost_sign * equipment.startup_cost.get_value(window.first_date())
                if config.order_type == OrderType.Buy:
                    q = sum(target_planning.get_value(t) for t in window.index)
                else:
                    q = sum(equipment.minimum_power.get_value(t) for t in window.index)

                if q == 0.0 and config.order_type == OrderType.Sell:
                    cfg.logger.warning(
                        f"Null Pmin for unit {equipment.name}. Start up cost is either null or neglected."
                    )
                elif q == 0.0 and config.order_type == OrderType.Buy:
                    # Fallback: spread over Pmin when the target planning is zero (conservative estimate)
                    pmin_total = sum(equipment.minimum_power.get_value(t) for t in window.index)
                    if pmin_total == 0:
                        cfg.logger.warning(
                            f"Null Pmin for unit {equipment.name}. Start up cost is either null or neglected."
                        )
                    else:
                        startup_cost_per_mw = total_startup_cost / pmin_total
                else:
                    startup_cost_per_mw = total_startup_cost / q

            inflexible_bids: list[tuple[DateTime, Order]] = []

            t = parent_date.add(minutes=-parameters.temporal.timestep.in_minutes() * direction)
            for _ in range(number_of_indexes):
                t = t.add(minutes=parameters.temporal.timestep.in_minutes() * direction)

                cleared_power = cleared_engagement.get_value(t)
                target_power = target_planning.get_value(t)
                pmin = equipment.minimum_power.get_value(t)

                # Volumes offered depend on the window type:
                # - Modulation: only a flexible block covering the delta between plannings.
                # - Sell (startup/extension): flexible above Pmin + inflexible block at Pmin.
                # - Buy (shutdown/shortening): flexible down to Pmin + inflexible at full previous power.
                #   (inflexible and flexible are EXCLUSION-coupled, so submitted volume = inflexible)
                if is_modulation:
                    q_max_flexible = (
                        target_power - cleared_power
                        if config.order_type == OrderType.Sell
                        else cleared_power - target_power
                    )
                    q_inflexible = 0.0
                    if config.order_type == OrderType.Sell:
                        sell_values[t_to_idx[t]] += q_max_flexible
                    else:
                        buy_values[t_to_idx[t]] += q_max_flexible
                elif config.order_type == OrderType.Sell:
                    q_max_flexible = target_power - pmin
                    q_inflexible = pmin - cleared_power
                    sell_values[t_to_idx[t]] += q_max_flexible + q_inflexible
                else:
                    q_max_flexible = cleared_power - pmin
                    q_inflexible = cleared_power
                    buy_values[t_to_idx[t]] += q_inflexible

                # TODO: subtract intraday ISP imbalance adjustment from base_price once implemented
                base_price = equipment.variable_cost.get_value(t)

                flexible_bid = None
                if q_max_flexible > parameters.allowed_round_off_error:
                    order_name = f"ID_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}_{equipment.name}_{t.format('YYYY_MM_DD_HH_mm_ss')}_flexible_{window.window_type.value}"
                    flexible_bid = build_intraday_order(
                        equipment, order_name, base_price, 0.0, q_max_flexible, config.order_type, t, parameters
                    )
                    orders.append(flexible_bid)

                if q_inflexible > parameters.allowed_round_off_error:
                    order_name = f"ID_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}_{equipment.name}_{t.format('YYYY_MM_DD_HH_mm_ss')}_inflexible_{window.window_type.value}"
                    inflexible_bid = build_intraday_order(
                        equipment,
                        order_name,
                        base_price + startup_cost_per_mw,
                        q_inflexible,
                        q_inflexible,
                        config.order_type,
                        t,
                        parameters,
                    )
                    orders.append(inflexible_bid)
                    inflexible_bids.append((t, inflexible_bid))

                    if flexible_bid is not None:
                        couplings.append(
                            OrderCoupling(
                                name=f"{config.flex_inflex_coupling}_ID_{equipment.name}_{t.format('YYYY_MM_DD_HH_mm_ss')}_{window.window_type.value}_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}",
                                coupling_type=config.flex_inflex_coupling,
                                orders=[inflexible_bid, flexible_bid],
                            )
                        )
                elif not is_modulation:
                    cfg.logger.warning(
                        f"Unrecognised name of sequence : {window.window_type.value}, for unit {equipment.name} between {window.first_date()} and {window.last_date()}"
                    )

            # Chain inflexible blocks across timesteps so the market sees the full commitment structure.
            if number_of_indexes > 1 and config.chaining != InflexibleChaining.NONE and len(inflexible_bids) > 1:
                for k in range(len(inflexible_bids) - 1):
                    ts, bid = inflexible_bids[k]
                    _, next_bid = inflexible_bids[k + 1]
                    couplings.append(
                        OrderCoupling(
                            name=f"par_chil_id_{equipment.name}_{ts.format('DD_MM_YYYY_HH_mm_ss')}_{window.window_type.value}_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}",
                            coupling_type=CouplingType.PARENT_CHILDREN,
                            orders=[bid, next_bid],
                        )
                    )
                if config.chaining == InflexibleChaining.RING:
                    # Close the ring: last inflexible block is coupled back to the first,
                    # so the entire commitment sequence is accepted or rejected as a unit.
                    ts, bid = inflexible_bids[-1]
                    couplings.append(
                        OrderCoupling(
                            name=f"par_chil_id_{equipment.name}_{ts.format('DD_MM_YYYY_HH_mm_ss')}_{window.window_type.value}_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}",
                            coupling_type=CouplingType.PARENT_CHILDREN,
                            orders=[bid, inflexible_bids[0][1]],
                        )
                    )

        return orders, couplings, sell_values, buy_values

    def _formulate_peak(
        self,
        equipment: ThermalIDO,
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling], list[float], list[float]]:
        """Formulate orders for PEAK thermal units.

        PEAK units are offered independently per timestep (no window grouping):
        - If the unit is currently off and can start: inflexible sell at Pmin (with startup cost)
          coupled to an optional flexible sell for capacity above Pmin.
        - If the unit is already running: flexible sell for remaining headroom above current power.
        - If over-committed (running above Pmin): flexible buy to allow partial de-commitment.
        """
        orders: list[Order] = []
        couplings: list[OrderCoupling] = []
        sell_values: list[float] = [0.0] * len(orders_timestamps)
        buy_values: list[float] = [0.0] * len(orders_timestamps)
        cleared_engagement = engaged_quantity(equipment, parameters)

        for i, t in enumerate(orders_timestamps):
            minimum_power = equipment.minimum_power.get_value(t)
            maximum_power = equipment.maximum_power.get_value(t)

            if maximum_power == 0.0 or maximum_power < minimum_power:
                cfg.logger.warning(
                    f"Maximum power of unit {equipment.name} is null or lower than minimum power at time {str(t)}. No order will therefore be created."
                )
                continue

            pow_t = 0.0 if cleared_engagement is None else cleared_engagement.get_value(t)
            unit_is_off = pow_t == 0.0
            has_minimum_power = minimum_power > 0

            if has_minimum_power and unit_is_off:
                min_hours_on = 0.0
                if equipment.minimum_time_on is not None:
                    min_hours_on = (
                        1.0 if equipment.minimum_time_on.in_hours() == 0.0 else equipment.minimum_time_on.in_hours()
                    )
                # Startup cost amortised over (Pmin × minimum run duration)
                price = equipment.startup_cost.get_value(t) / (
                    minimum_power * min_hours_on
                ) + equipment.variable_cost.get_value(t)

                inflexible_bid_name = f"id_inflex_s_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}_{equipment.name}_{t.format('DD_MM_YYYY_HH_mm_ss')}"
                inflexible_bid = build_intraday_order(
                    equipment, inflexible_bid_name, price, minimum_power, minimum_power, OrderType.Sell, t, parameters
                )
                orders.append(inflexible_bid)
                sell_values[i] += minimum_power

                q_max = maximum_power - minimum_power
                if q_max > parameters.allowed_round_off_error:
                    flexible_bid_name = f"id_flex_s_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}_{equipment.name}_{t.format('DD_MM_YYYY_HH_mm_ss')}"
                    flexible_bid = build_intraday_order(
                        equipment,
                        flexible_bid_name,
                        equipment.variable_cost.get_value(t),
                        0.0,
                        q_max,
                        OrderType.Sell,
                        t,
                        parameters,
                    )
                    orders.append(flexible_bid)
                    sell_values[i] += q_max
                    couplings.append(
                        OrderCoupling(
                            name=f"pc_id_inflex_flex_s_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}_{equipment.name}_{t.format('DD_MM_YYYY_HH_mm_ss')}",
                            coupling_type=CouplingType.PARENT_CHILDREN,
                            orders=[inflexible_bid, flexible_bid],
                        )
                    )
            else:
                # Unit already running (or no Pmin): offer remaining headroom above current output.
                q_max = maximum_power - pow_t
                if q_max > parameters.allowed_round_off_error:
                    flexible_bid_name = f"id_flex_s_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}_{equipment.name}_{t.format('DD_MM_YYYY_HH_mm_ss')}"
                    flexible_bid = build_intraday_order(
                        equipment,
                        flexible_bid_name,
                        equipment.variable_cost.get_value(t),
                        0.0,
                        q_max,
                        OrderType.Sell,
                        t,
                        parameters,
                    )
                    orders.append(flexible_bid)
                    sell_values[i] += q_max

            # If unit is over-committed above Pmin, offer a flexible buy to reduce output.
            if pow_t != 0.0 and pow_t != minimum_power:
                q_max = pow_t - minimum_power
                if q_max > parameters.allowed_round_off_error:
                    flexible_bid_name = f"id_flex_b_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}_{equipment.name}_{t.format('DD_MM_YYYY_HH_mm_ss')}"
                    flexible_bid = build_intraday_order(
                        equipment,
                        flexible_bid_name,
                        equipment.variable_cost.get_value(t),
                        0.0,
                        q_max,
                        OrderType.Buy,
                        t,
                        parameters,
                    )
                    orders.append(flexible_bid)
                    buy_values[i] += q_max

        return orders, couplings, sell_values, buy_values
