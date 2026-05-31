"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.modules.day_ahead_orders.input_objects.order import OrderDAO
from atlas.modules.day_ahead_orders.input_objects.order_coupling import OrderCouplingDAO
from atlas.modules.day_ahead_orders.input_objects.thermal import ThermalDAO
from atlas.modules.day_ahead_orders.parameters import DayAheadOrdersParameters
from atlas.modules.day_ahead_orders.steps.thermal.dispatch.state_sequence import build_baseload_state_sequence
from atlas.modules.day_ahead_orders.steps.thermal.orders.online_sequences import extract_online_sequences
from atlas.modules.day_ahead_orders.steps.thermal.orders.unit_orders import formulate_unit_orders


class ThermalBaseLoadOrders:
    """Order formulation for baseload thermal units (rule-based, no LP)."""

    def __init__(self, orders_time: list[DateTime], parameters: DayAheadOrdersParameters):
        self.orders_time = orders_time
        self.parameters = parameters

    def formulate(self, unit: ThermalDAO) -> tuple[list[OrderDAO], list[OrderCouplingDAO]]:
        """
        Formulate orders for a thermic baseload unit.

        :param unit: the thermal unit to formulate orders for
        :return: orders and order couplings generated for this unit
        """
        orders: list[OrderDAO] = []
        couplings: list[OrderCouplingDAO] = []

        states_sequence, inconsistent = build_baseload_state_sequence(unit, self.parameters)
        if inconsistent:
            cfg.logger.warning(
                f"Equipment {unit.name}'s states sequence is inconsistent. No orders have been formulated for this unit"
            )
            return orders, couplings

        for online_timeframe, case_name in extract_online_sequences(
            states_sequence, self.orders_time, self.parameters.temporal.timestep
        ):
            unit_orders, unit_couplings = formulate_unit_orders(
                online_timeframe, unit, self.orders_time, self.parameters, case=case_name
            )
            orders.extend(unit_orders)
            couplings.extend(unit_couplings)

        return orders, couplings
