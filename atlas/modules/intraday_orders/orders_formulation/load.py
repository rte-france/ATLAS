"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas.enums import LoadType, OrderType
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.input_objects.load import LoadIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order, engaged_quantity
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


class LoadOrdersFormulator(AbstractOrdersFormulator[LoadIDO]):
    EQUIPMENT_TYPE_NAME = "load"

    def formulate_equipment_orders(
        self,
        equipment: LoadIDO,
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling], Timeseries, Timeseries]:
        orders: list[Order] = []
        sell_values: list[float] = [0.0] * len(orders_timestamps)
        buy_values: list[float] = [0.0] * len(orders_timestamps)
        cleared_engagement = engaged_quantity(equipment, parameters)

        if equipment.load_type == LoadType.POWER_TO_GAS:
            # POWER_TO_GAS loads can flex their consumption between zero and maximum_power_forecast.
            # Selling means reducing consumption (freeing up power on the grid).
            # Buying means increasing consumption (absorbing surplus power).
            target_planning = equipment.maximum_power_forecast.get_forecast(
                parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
            )
            consumption_headroom = cleared_engagement - target_planning

            for i, t in enumerate(orders_timestamps):
                # Positive headroom: engagement > plan → can increase consumption further (buy).
                expandable_consumption = consumption_headroom.get_value(t)
                # Current engagement: the committed consumption that can be reduced (sell).
                reducible_consumption = cleared_engagement.get_value(t)

                if expandable_consumption > parameters.allowed_round_off_error:
                    bid = self._build_offer(
                        equipment,
                        equipment.variable_cost.get_value(t),
                        expandable_consumption,
                        OrderType.Buy,
                        t,
                        parameters,
                    )
                    orders.append(bid)
                    buy_values[i] += abs(expandable_consumption)

                if abs(reducible_consumption) > parameters.allowed_round_off_error:
                    bid = self._build_offer(
                        equipment,
                        equipment.variable_cost.get_value(t),
                        abs(reducible_consumption),
                        OrderType.Sell,
                        t,
                        parameters,
                    )
                    orders.append(bid)
                    sell_values[i] += abs(reducible_consumption)

        else:
            # Standard load: compare cleared engagement to the new consumption forecast.
            # consumption_delta > 0: consuming more than planned → buy the extra.
            # consumption_delta < 0: consuming less than planned → sell back the surplus.
            target_planning = equipment.maximum_power_forecast.get_forecast(
                parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
            )
            consumption_delta = cleared_engagement - target_planning

            for i, t in enumerate(orders_timestamps):
                consumption_value = consumption_delta.get_value(t)

                if consumption_value > parameters.allowed_round_off_error:
                    bid = self._build_offer(
                        equipment, parameters.load_price, consumption_value, OrderType.Buy, t, parameters
                    )
                    orders.append(bid)
                    buy_values[i] += abs(consumption_value)

                elif abs(consumption_value) > parameters.allowed_round_off_error:
                    bid = self._build_offer(equipment, 0.0, abs(consumption_value), OrderType.Sell, t, parameters)
                    orders.append(bid)
                    sell_values[i] += abs(consumption_value)

        sell_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, sell_values
        )
        buy_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, buy_values
        )
        return orders, [], sell_submitted_volume, buy_submitted_volume

    def _build_offer(
        self,
        equipment: LoadIDO,
        price: float,
        qmax: float,
        order_type: OrderType,
        time: DateTime,
        parameters: IntradayOrdersParameters,
    ) -> Order:
        bid_name = f"{order_type.value.lower()}_id_order_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}_{equipment.name}_{time.format('DD_MM_YYYY_HH_mm_ss')}"
        return build_intraday_order(equipment, bid_name, price, 0.0, qmax, order_type, time, parameters)
