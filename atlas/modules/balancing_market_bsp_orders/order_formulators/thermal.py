"""Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements ThermalOrderFormulator.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import CouplingType, OrderType
from atlas.modules.balancing_market_bsp_orders.order_formulators.base import AbstractOrderFormulator
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


class ThermalOrderFormulator(AbstractOrderFormulator):
    """Formulates balancing orders for thermal equipment."""

    def formulate(self) -> tuple[list[Order], list[OrderCoupling]]:
        """
        Formulate upward and downward orders for the thermal equipment.

        :return: Tuple of formulated orders and their couplings
        :rtype: tuple[list[Order], list[OrderCoupling]]
        """
        start = self.parameters.temporal.start_date
        end = self.parameters.temporal.end_date - self.parameters.temporal.timestep
        execution_date = self.parameters.temporal.execution_date
        timestep_minutes = int(self._timestep_minutes)

        forecasted_power = self.equipment.power.get_forecast(execution_date, start, end)
        max_power = self.equipment.maximum_power.slice(start, end)
        min_power = self.equipment.minimum_power.slice(start, end)

        upward_procured, downward_procured = self.compute_procured_power(
            execution_date, start, end, self.parameters.product_type
        )

        upward_available = max_power - forecasted_power - upward_procured
        downward_available = forecasted_power - min_power - downward_procured

        orders: list[Order] = []
        couplings: list[OrderCoupling] = []

        for time in self.target_times:
            if not self.is_after_setup_delay(time):
                continue

            power_at_time = forecasted_power.get_value(time)
            if 0 < power_at_time < min_power.get_value(time):
                upward_available.set_value(time, 0.0)
                downward_available.set_value(time, 0.0)

            next_time = time.add(minutes=timestep_minutes)

            qmax_up = max(0.0, upward_available.get_value(time))
            qmax_down = max(0.0, downward_available.get_value(time))

            if self.equipment.maximum_gradient != 0:
                qmax_up, qmax_down = self._apply_gradient_constraint(forecasted_power, time, qmax_up, qmax_down)

            startup_case = self._classify_startup_case(forecasted_power, time)

            if startup_case == "case_5":
                start_orders, start_couplings = self._formulate_case_5_orders(time, next_time)
                orders.extend(start_orders)
                couplings.extend(start_couplings)
            elif startup_case == "case_1":
                order = self._formulate_case_1_order(time, next_time)
                if order is not None:
                    orders.append(order)
            elif startup_case == "case_2":
                order = self._formulate_case_2_order(time, next_time)
                if order is not None:
                    orders.append(order)
            elif startup_case == "case_3":
                order = self._formulate_case_3_order(time, next_time)
                if order is not None:
                    orders.append(order)
            else:
                order = self._formulate_plain_upward_order(time, next_time, qmax_up)
                if order is not None:
                    orders.append(order)

            order = self._formulate_downward_order(time, next_time, qmax_down)
            if order is not None:
                orders.append(order)

        cfg.logger.info(f"Formulation of orders on equipment {self.equipment.name} completed")
        return orders, couplings

    @property
    def _timestep_minutes(self) -> float:
        """Timestep duration in minutes, as a float."""
        return self.parameters.temporal.timestep.total_seconds() / 60

    def _forecasted_power_at(self, time: DateTime) -> float:
        """
        Return the forecasted power at a given time, or 0.0 if unavailable (e.g. outside
        the forecast matrix's covered range).

        :param time: Time to evaluate
        :type time: DateTime
        :return: Forecasted power at that time, or 0.0 if unavailable
        :rtype: float
        """
        execution_date = self.parameters.temporal.execution_date
        try:
            return self.equipment.power.get_forecast(execution_date, time, time).get_value(time)
        except (KeyError, ValueError):
            return 0.0

    def _neighbor_power(self, time: DateTime, forward: bool) -> float:
        """
        Return the forecasted power one timestep before or after the given time.

        :param time: Reference timestep
        :type time: DateTime
        :param forward: True to look at the next timestep, False for the previous one
        :type forward: bool
        :return: Forecasted power at the neighboring timestep, or 0.0 if unavailable
        :rtype: float
        """
        offset_minutes = int(self._timestep_minutes)
        neighbor_time = time.add(minutes=offset_minutes) if forward else time.subtract(minutes=offset_minutes)
        return self._forecasted_power_at(neighbor_time)

    def _startup_cost_at(self, time: DateTime) -> float:
        """
        Return the startup cost at a given time, or 0.0 if not defined on the equipment.

        :param time: Time to evaluate
        :type time: DateTime
        :return: Startup cost, or 0.0 if `startup_cost` is None
        :rtype: float
        """
        if self.equipment.startup_cost is None:
            return 0.0
        return self.equipment.startup_cost.get_value(time)

    def _has_stable_power_before(self, time: DateTime) -> bool:
        """
        Check whether the equipment's forecasted power stayed constant for at least
        minimum_stable_power_duration in the timesteps before the given time. A power
        of 0 at the immediately preceding timestep is treated as trivially satisfied —
        that side is governed by the minimum_time_off constraint instead.

        :param time: Reference timestep (order start/end time)
        :type time: DateTime
        :return: True if enough stable history exists (or the preceding power is 0)
        :rtype: bool
        """
        duration_requirement = self.equipment.minimum_stable_power_duration
        offset_minutes = int(self._timestep_minutes)
        reference_time = time.subtract(minutes=offset_minutes)

        studied_time = reference_time
        studied_power = self._forecasted_power_at(studied_time)
        previous_power = studied_power

        if previous_power == 0:
            return True

        while studied_power == previous_power and (reference_time - studied_time) < duration_requirement:
            previous_power = studied_power
            studied_time = studied_time.subtract(minutes=offset_minutes)
            studied_power = self._forecasted_power_at(studied_time)

        return duration_requirement <= (reference_time - studied_time)

    def _has_stable_power_after(self, time: DateTime) -> bool:
        """
        Same as _has_stable_power_before but looking forward from `time`.

        :param time: Reference timestep (order start/end time)
        :type time: DateTime
        :return: True if enough stable future exists (or the following power is 0)
        :rtype: bool
        """
        duration_requirement = self.equipment.minimum_stable_power_duration
        offset_minutes = int(self._timestep_minutes)
        reference_time = time.add(minutes=offset_minutes)

        studied_time = reference_time
        studied_power = self._forecasted_power_at(studied_time)
        previous_power = studied_power

        if previous_power == 0:
            return True

        while studied_power == previous_power and (studied_time - reference_time) < duration_requirement:
            previous_power = studied_power
            studied_time = studied_time.add(minutes=offset_minutes)
            studied_power = self._forecasted_power_at(studied_time)

        return duration_requirement <= (studied_time - reference_time)

    def _apply_minimum_stable_power_duration_constraint(
        self,
        time: DateTime,
        order_type: OrderType,
        power_available: float,
    ) -> tuple[float, bool, bool]:
        """
        MSPD check for a single-timestep order. No-op if MSPD is shorter than the
        timestep. Otherwise the equipment needs to have been flat for long enough
        before `time`, or the order's invalid.

        TODO: forward check

        :param time: order start/end time
        :type time: DateTime
        :param power_available: qty before this constraint
        :type power_available: float
        :return: (power_available, is_valid, is_undivisible)
        :rtype: tuple[float, bool, bool]
        """
        duration_requirement = self.equipment.minimum_stable_power_duration
        timestep = self.parameters.temporal.timestep

        if duration_requirement < timestep:
            return power_available, True, False

        if not self._has_stable_power_before(time):
            return 0.0, False, False

        if not self._has_stable_power_after(time):
            return 0.0, False, False

        is_valid_order = True
        is_order_undivisible = False

        if timestep < duration_requirement:
            is_valid_order = False

            starting_power = self._forecasted_power_at(time)
            previous_power = self._neighbor_power(time, forward=False)
            next_power = self._neighbor_power(time, forward=True)

            if previous_power != starting_power:
                if next_power != starting_power:
                    return 0.0, False, False
                if previous_power == 0:
                    return 0.0, False, False

                is_order_undivisible = True
                delta = previous_power - starting_power
                if delta > 0:
                    if order_type == OrderType.Sell:
                        power_available, is_valid_order = delta, True
                    else:
                        power_available, is_valid_order = 0.0, False
                else:
                    if order_type == OrderType.Buy:
                        power_available, is_valid_order = starting_power - previous_power, True
                    else:
                        power_available, is_valid_order = 0.0, False

            if next_power != starting_power:
                if next_power == 0:
                    return 0.0, False, False

                is_order_undivisible = True
                delta = next_power - starting_power
                if delta > 0:
                    if order_type == OrderType.Sell:
                        power_available, is_valid_order = delta, True
                    else:
                        power_available, is_valid_order = 0.0, False
                else:
                    if order_type == OrderType.Buy:
                        power_available, is_valid_order = starting_power - next_power, True
                    else:
                        power_available, is_valid_order = 0.0, False

        return power_available, is_valid_order, is_order_undivisible

    def _formulate_plain_upward_order(self, time: DateTime, next_time: DateTime, qmax_up: float) -> Order | None:
        """
        Regular upward order (no startup involved), after the MSPD check.

        :param time: order start/end time
        :type time: DateTime
        :param next_time: time + timestep
        :type next_time: DateTime
        :param qmax_up: qty before MSPD
        :type qmax_up: float
        :return: the order, or None if invalid / under 1 MW
        :rtype: Order | None
        """
        qmax_up, is_valid, is_undivisible = self._apply_minimum_stable_power_duration_constraint(
            time, OrderType.Sell, qmax_up
        )
        if not is_valid or qmax_up < 1.0:
            return None

        return self.build_order(
            order_type=OrderType.Sell,
            start=time,
            end=next_time,
            price=self.equipment.variable_cost.get_value(time),
            qmin=qmax_up if is_undivisible else 0.0,
            qmax=qmax_up,
        )

    def _formulate_downward_order(self, time: DateTime, next_time: DateTime, qmax_down: float) -> Order | None:
        """
        Downward order, after the MSPD check.

        :param time: order start/end time
        :type time: DateTime
        :param next_time: time + timestep
        :type next_time: DateTime
        :param qmax_down: qty before MSPD
        :type qmax_down: float
        :return: the order, or None if invalid / under 1 MW
        :rtype: Order | None
        """
        qmax_down, is_valid, is_undivisible = self._apply_minimum_stable_power_duration_constraint(
            time, OrderType.Buy, qmax_down
        )
        if not is_valid or qmax_down < 1.0:
            return None

        return self.build_order(
            order_type=OrderType.Buy,
            start=time,
            end=next_time,
            price=self.equipment.variable_cost.get_value(time),
            qmin=qmax_down if is_undivisible else 0.0,
            qmax=qmax_down,
        )

    def _formulate_case_1_order(self, time: DateTime, next_time: DateTime) -> Order | None:
        """
        Formulate the bounded upward order for Case 1 (equipment was ON both before and
        after this timestep): a single order bounded between previous and next forecasted
        power. Price is reduced by the cancelled startup cost, since this order avoids a
        startup that would otherwise have been needed.

        Deviation from legacy: the gradient feasibility check uses
        'maximum_gradient * timestep_minutes' (consistent with the rest of the module)
        instead of the legacy's hardcoded 'maximum_gradient * 60'.

        :param time: Order start/end time (single timestep)
        :type time: DateTime
        :param next_time: Order end boundary (time + timestep)
        :type next_time: DateTime
        :return: The bounded Sell order, or None if invalid or qmax rounds below 1 MW
        :rtype: Order | None
        """
        previous_power = self._neighbor_power(time, forward=False)
        next_power = self._neighbor_power(time, forward=True)

        max_gradient = self.equipment.maximum_gradient
        if max_gradient > 0 and abs(next_power - previous_power) > 2 * (max_gradient * self._timestep_minutes):
            return None

        max_power_at_time = self.equipment.maximum_power.get_value(time)
        min_power_at_time = self.equipment.minimum_power.get_value(time)

        if max_gradient > 0:
            max_grad = max_gradient * self._timestep_minutes
            if next_power >= previous_power:
                bounded_qmax = min(max_power_at_time, previous_power + max_grad)
                bounded_qmin = max(min_power_at_time, next_power - max_grad)
            else:
                bounded_qmax = min(max_power_at_time, next_power + max_grad)
                bounded_qmin = max(min_power_at_time, previous_power - max_grad)
        else:
            bounded_qmax = max_power_at_time
            bounded_qmin = min_power_at_time

        bounded_qmax, is_valid, is_undivisible = self._apply_minimum_stable_power_duration_constraint(
            time, OrderType.Sell, bounded_qmax
        )
        if not is_valid:
            return None
        if is_undivisible:
            bounded_qmin = bounded_qmax

        if bounded_qmax < 1.0 or bounded_qmin > bounded_qmax:
            return None

        duration_hours = self._timestep_minutes / 60
        price = self.equipment.variable_cost.get_value(time) - self._startup_cost_at(time) / (
            bounded_qmax * duration_hours
        )
        price = round(max(price, 0.0), 2)

        return self.build_order(
            order_type=OrderType.Sell,
            start=time,
            end=next_time,
            price=price,
            qmin=bounded_qmin,
            qmax=bounded_qmax,
        )

    def _formulate_case_2_order(self, time: DateTime, next_time: DateTime) -> Order | None:
        """
        Formulate the bounded upward order for Case 2 (equipment was ON before this
        timestep, OFF after): a single order (no startup split), bounded between the
        previous forecasted power and the previous power plus one gradient step.

        :param time: Order start/end time (single timestep)
        :type time: DateTime
        :param next_time: Order end boundary (time + timestep)
        :type next_time: DateTime
        :return: The bounded Sell order, or None if invalid or qmax rounds below 1 MW
        :rtype: Order | None
        """
        if not self._check_on_off_time_requirement(time, searching_on=False, searching_backwards=False):
            return None

        previous_power = self._neighbor_power(time, forward=False)

        max_power_at_time = self.equipment.maximum_power.get_value(time)
        min_power_at_time = self.equipment.minimum_power.get_value(time)

        if self.equipment.maximum_gradient > 0:
            max_grad = self.equipment.maximum_gradient * self._timestep_minutes
            bounded_qmax = min(max_power_at_time, previous_power + max_grad)
        else:
            bounded_qmax = max_power_at_time

        bounded_qmin = max(min_power_at_time, previous_power)

        bounded_qmax, is_valid, is_undivisible = self._apply_minimum_stable_power_duration_constraint(
            time, OrderType.Sell, bounded_qmax
        )
        if not is_valid:
            return None
        if is_undivisible:
            bounded_qmin = bounded_qmax

        if bounded_qmax < 1.0 or bounded_qmin > bounded_qmax:
            return None

        return self.build_order(
            order_type=OrderType.Sell,
            start=time,
            end=next_time,
            price=self.equipment.variable_cost.get_value(time),
            qmin=bounded_qmin,
            qmax=bounded_qmax,
        )

    def _formulate_case_3_order(self, time: DateTime, next_time: DateTime) -> Order | None:
        """
        Formulate the bounded upward order for Case 3 (equipment was OFF before this
        timestep, ON after): a single order (no startup split), bounded between the
        next forecasted power and the next power plus one gradient step.

        :param time: Order start/end time (single timestep)
        :type time: DateTime
        :param next_time: Order end boundary (time + timestep)
        :type next_time: DateTime
        :return: The bounded Sell order, or None if invalid or qmax rounds below 1 MW
        :rtype: Order | None
        """
        execution_date = self.parameters.temporal.execution_date

        if (time - execution_date) < self.equipment.startup_duration:
            return None

        if not self._check_on_off_time_requirement(time, searching_on=False, searching_backwards=True):
            return None

        next_power = self._neighbor_power(time, forward=True)

        max_power_at_time = self.equipment.maximum_power.get_value(time)
        min_power_at_time = self.equipment.minimum_power.get_value(time)

        if self.equipment.maximum_gradient > 0:
            max_grad = self.equipment.maximum_gradient * self._timestep_minutes
            bounded_qmax = min(max_power_at_time, next_power + max_grad)
        else:
            bounded_qmax = max_power_at_time

        bounded_qmin = max(min_power_at_time, next_power)

        bounded_qmax, is_valid, is_undivisible = self._apply_minimum_stable_power_duration_constraint(
            time, OrderType.Sell, bounded_qmax
        )
        if not is_valid:
            return None
        if is_undivisible:
            bounded_qmin = bounded_qmax

        if bounded_qmax < 1.0 or bounded_qmin > bounded_qmax:
            return None

        return self.build_order(
            order_type=OrderType.Sell,
            start=time,
            end=next_time,
            price=self.equipment.variable_cost.get_value(time),
            qmin=bounded_qmin,
            qmax=bounded_qmax,
        )

    def _formulate_case_5_orders(
        self,
        time: DateTime,
        next_time: DateTime,
    ) -> tuple[list[Order], list[OrderCoupling]]:
        """
        Formulate the split startup orders for a full startup (Case 5): an indivisible
        '_start1' order up to minimum_power, priced with the startup cost spread over
        its quantity and duration, and a divisible '_start2' order above minimum_power
        at the regular variable cost. The two are linked by a PARENT_CHILDREN coupling.

        :param time: Order start time (== order end time, single timestep)
        :type time: DateTime
        :param next_time: Order end boundary (time + timestep)
        :type next_time: DateTime
        :return: Tuple of (orders, couplings), both empty if the startup is not valid
        :rtype: tuple[list[Order], list[OrderCoupling]]
        """
        execution_date = self.parameters.temporal.execution_date

        if (time - execution_date) < self.equipment.startup_duration:
            return [], []

        if not self._check_on_off_time_requirement(time, searching_on=False, searching_backwards=True):
            return [], []

        if not self._check_on_off_time_requirement(time, searching_on=False, searching_backwards=False):
            return [], []

        if self.parameters.temporal.timestep < self.equipment.minimum_time_on:
            return [], []

        max_power_at_time = self.equipment.maximum_power.get_value(time)
        min_power_at_time = self.equipment.minimum_power.get_value(time)

        _, is_valid, _ = self._apply_minimum_stable_power_duration_constraint(time, OrderType.Sell, max_power_at_time)
        if not is_valid:
            return [], []

        duration_hours = self._timestep_minutes / 60
        startup_cost = self._startup_cost_at(time)

        start1_qmax = min_power_at_time
        start1_price = round(
            self.equipment.variable_cost.get_value(time) + startup_cost / (start1_qmax * duration_hours), 2
        )
        order_1 = self.build_order(
            order_type=OrderType.Sell,
            start=time,
            end=next_time,
            price=start1_price,
            qmin=start1_qmax,
            qmax=start1_qmax,
            suffix="_start1",
        )

        start2_qmax = max_power_at_time - min_power_at_time
        order_2 = self.build_order(
            order_type=OrderType.Sell,
            start=time,
            end=next_time,
            price=self.equipment.variable_cost.get_value(time),
            qmin=0.0,
            qmax=start2_qmax,
            suffix="_start2",
        )

        if order_1 is None or order_2 is None:
            return [], []

        coupling = OrderCoupling(
            name=f"parent_children_{order_1.name}",
            orders=[order_1, order_2],
            coupling_type=CouplingType.PARENT_CHILDREN,
        )
        return [order_1, order_2], [coupling]

    def _classify_startup_case(
        self,
        forecasted_power,
        time: DateTime,
    ) -> str:
        """
        Classify the equipment's on/off transition case at a given timestep.

        Mirrors the legacy Cases 1-5 used to determine whether an upward order at
        this timestep requires a startup, cancels one, or is invalid.

        :param forecasted_power: Forecasted power timeseries over the balancing time frame
        :type forecasted_power: Timeseries
        :param time: The timestep being evaluated
        :type time: DateTime
        :return: One of 'no_startup', 'case_1', 'case_2', 'case_3', 'case_5'
        :rtype: str
        """
        power_at_time = forecasted_power.get_value(time)
        if power_at_time != 0:
            return "no_startup"

        if self.equipment.minimum_power.get_value(time) <= 0:
            return "no_startup"

        previous_power = self._neighbor_power(time, forward=False)
        next_power = self._neighbor_power(time, forward=True)

        if previous_power > 0 and next_power > 0:
            return "case_1"
        if previous_power > 0:
            return "case_2"
        if next_power > 0:
            return "case_3"
        return "case_5"

    def _check_on_off_time_requirement(
        self,
        current_time: DateTime,
        searching_on: bool = True,
        searching_backwards: bool = True,
    ) -> bool:
        """
        Check whether the equipment satisfies a minimum on/off duration requirement
        around a given timestep.

        :param current_time: The reference timestep
        :type current_time: DateTime
        :param searching_on: True to check MinimumTimeOn, False to check MinimumTimeOff
        :type searching_on: bool
        :param searching_backwards: True to search before current_time, False to search after
        :type searching_backwards: bool
        :return: True if the duration requirement is met
        :rtype: bool
        """
        timestep_seconds = self.parameters.temporal.timestep.total_seconds()
        duration_requirement = self.equipment.minimum_time_on if searching_on else self.equipment.minimum_time_off

        def _step(t: DateTime) -> DateTime:
            return t.subtract(seconds=timestep_seconds) if searching_backwards else t.add(seconds=timestep_seconds)

        def _elapsed(t: DateTime):
            return (current_time - t) if searching_backwards else (t - current_time)

        studied_time = _step(current_time)
        power = self._forecasted_power_at(studied_time)
        condition = (lambda pw: pw != 0) if searching_on else (lambda pw: pw == 0)

        while condition(power) and _elapsed(studied_time) <= duration_requirement:
            studied_time = _step(studied_time)
            power = self._forecasted_power_at(studied_time)

        return duration_requirement < _elapsed(studied_time)
