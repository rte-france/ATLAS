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
        timestep_minutes = int(self.parameters.temporal.timestep.total_seconds() // 60)

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
            elif qmax_up >= 1.0:
                order = self.build_order(
                    order_type=OrderType.Sell,
                    start=time,
                    end=next_time,
                    price=self.equipment.variable_cost.get_value(time),
                    qmin=0.0,
                    qmax=qmax_up,
                )
                if order is not None:
                    orders.append(order)

            if qmax_down < 1.0:
                continue

            order = self.build_order(
                order_type=OrderType.Buy,
                start=time,
                end=next_time,
                price=self.equipment.variable_cost.get_value(time),
                qmin=0.0,
                qmax=qmax_down,
            )
            if order is not None:
                orders.append(order)

        cfg.logger.info(f"Formulation of orders on equipment {self.equipment.name} completed")
        return orders, couplings

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
        timestep = self.parameters.temporal.timestep
        execution_date = self.parameters.temporal.execution_date
        timestep_minutes = timestep.total_seconds() / 60
        previous_time = time.subtract(minutes=int(timestep_minutes))
        next_step_time = time.add(minutes=int(timestep_minutes))

        try:
            previous_power = self.equipment.power.get_forecast(execution_date, previous_time, previous_time).get_value(
                previous_time
            )
        except (KeyError, ValueError):
            previous_power = 0.0

        try:
            next_power = self.equipment.power.get_forecast(execution_date, next_step_time, next_step_time).get_value(
                next_step_time
            )
        except (KeyError, ValueError):
            next_power = 0.0

        max_gradient = self.equipment.maximum_gradient
        if max_gradient > 0 and abs(next_power - previous_power) > 2 * (max_gradient * timestep_minutes):
            return None

        max_power_at_time = self.equipment.maximum_power.get_value(time)
        min_power_at_time = self.equipment.minimum_power.get_value(time)

        if max_gradient > 0:
            max_grad = max_gradient * timestep_minutes
            if next_power >= previous_power:
                bounded_qmax = min(max_power_at_time, previous_power + max_grad)
                bounded_qmin = max(min_power_at_time, next_power - max_grad)
            else:
                bounded_qmax = min(max_power_at_time, next_power + max_grad)
                bounded_qmin = max(min_power_at_time, previous_power - max_grad)
        else:
            bounded_qmax = max_power_at_time
            bounded_qmin = min_power_at_time

        if bounded_qmax < 1.0 or bounded_qmin > bounded_qmax:
            return None

        duration_hours = timestep_minutes / 60
        startup_cost = self.equipment.startup_cost.get_value(time) if self.equipment.startup_cost is not None else 0.0
        price = self.equipment.variable_cost.get_value(time) - startup_cost / (bounded_qmax * duration_hours)
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

        timestep = self.parameters.temporal.timestep
        execution_date = self.parameters.temporal.execution_date
        previous_time = time.subtract(minutes=int(timestep.total_seconds() // 60))

        try:
            previous_power = self.equipment.power.get_forecast(execution_date, previous_time, previous_time).get_value(
                previous_time
            )
        except (KeyError, ValueError):
            previous_power = 0.0

        max_power_at_time = self.equipment.maximum_power.get_value(time)
        min_power_at_time = self.equipment.minimum_power.get_value(time)

        if self.equipment.maximum_gradient > 0:
            max_grad = self.equipment.maximum_gradient * (timestep.total_seconds() / 60)
            bounded_qmax = min(max_power_at_time, previous_power + max_grad)
        else:
            bounded_qmax = max_power_at_time

        bounded_qmin = max(min_power_at_time, previous_power)

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

        timestep = self.parameters.temporal.timestep
        next_step_time = time.add(minutes=int(timestep.total_seconds() // 60))

        try:
            next_power = self.equipment.power.get_forecast(execution_date, next_step_time, next_step_time).get_value(
                next_step_time
            )
        except (KeyError, ValueError):
            next_power = 0.0

        max_power_at_time = self.equipment.maximum_power.get_value(time)
        min_power_at_time = self.equipment.minimum_power.get_value(time)

        if self.equipment.maximum_gradient > 0:
            max_grad = self.equipment.maximum_gradient * (timestep.total_seconds() / 60)
            bounded_qmax = min(max_power_at_time, next_power + max_grad)
        else:
            bounded_qmax = max_power_at_time

        bounded_qmin = max(min_power_at_time, next_power)

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
        duration_hours = self.parameters.temporal.timestep.total_seconds() / 3600

        startup_cost = self.equipment.startup_cost.get_value(time) if self.equipment.startup_cost is not None else 0.0

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

        coupling = OrderCoupling(orders=[order_1, order_2], coupling_type=CouplingType.PARENT_CHILDREN)
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
        timestep = self.parameters.temporal.timestep
        execution_date = self.parameters.temporal.execution_date

        power_at_time = forecasted_power.get_value(time)
        if power_at_time != 0:
            return "no_startup"

        if self.equipment.minimum_power.get_value(time) <= 0:
            return "no_startup"

        previous_time = time.subtract(minutes=int(timestep.total_seconds() // 60))
        next_time = time.add(minutes=int(timestep.total_seconds() // 60))

        try:
            previous_power = self.equipment.power.get_forecast(execution_date, previous_time, previous_time).get_value(
                previous_time
            )
        except (KeyError, ValueError):
            previous_power = 0.0

        try:
            next_power = self.equipment.power.get_forecast(execution_date, next_time, next_time).get_value(next_time)
        except (KeyError, ValueError):
            next_power = 0.0

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
        execution_date = self.parameters.temporal.execution_date
        duration_requirement = self.equipment.minimum_time_on if searching_on else self.equipment.minimum_time_off

        def _step(t: DateTime) -> DateTime:
            return t.subtract(seconds=timestep_seconds) if searching_backwards else t.add(seconds=timestep_seconds)

        def _elapsed(t: DateTime):
            return (current_time - t) if searching_backwards else (t - current_time)

        def _power_at(t: DateTime) -> float:
            try:
                return self.equipment.power.get_forecast(execution_date, t, t).get_value(t)
            except (KeyError, ValueError):
                return 0.0

        studied_time = _step(current_time)
        power = _power_at(studied_time)
        condition = (lambda pw: pw != 0) if searching_on else (lambda pw: pw == 0)

        while condition(power) and _elapsed(studied_time) <= duration_requirement:
            studied_time = _step(studied_time)
            power = _power_at(studied_time)

        return duration_requirement < _elapsed(studied_time)
