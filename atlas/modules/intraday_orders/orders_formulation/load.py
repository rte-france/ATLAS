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
from atlas.modules.intraday_orders.utils import build_intraday_order
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


class LoadOrdersFormulator(AbstractOrdersFormulator[LoadIDO]):
    EQUIPMENT_TYPE_NAME = "load"

    def formulate_equipment_orders(
        self,
        equipment: LoadIDO,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling]]:
        orders: list[Order] = []
        consumption_engagement = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity

        if equipment.load_type == LoadType.POWER_TO_GAS:
            maximum_power = equipment.maximum_power_forecast.get_forecast(
                parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
            )
            available_power = consumption_engagement - maximum_power

            for t in orders_timestamps:
                available_down_power = available_power.get_value(t)
                available_up_power = consumption_engagement.get_value(t)

                if available_down_power > parameters.allowed_round_off_error:
                    bid_output = self.build_offer(
                        equipment,
                        equipment.variable_cost.get_value(t),
                        available_down_power,
                        OrderType.Buy,
                        t,
                        parameters,
                    )
                    orders.append(bid_output)
                    buy_submitted_volume.sum_value_at(t, abs(available_down_power))

                if abs(available_up_power) > parameters.allowed_round_off_error:
                    bid_output = self.build_offer(
                        equipment,
                        equipment.variable_cost.get_value(t),
                        available_up_power,
                        OrderType.Sell,
                        t,
                        parameters,
                    )
                    orders.append(bid_output)
                    sell_submitted_volume.sum_value_at(t, abs(available_up_power))

        else:
            consumption_new_planing = equipment.maximum_power_forecast.get_forecast(
                parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
            )
            consumption_forecast = consumption_engagement - consumption_new_planing

            for t in orders_timestamps:
                consumption_value = consumption_forecast.get_value(t)

                if consumption_value > parameters.allowed_round_off_error:
                    bid_output = self.build_offer(
                        equipment, parameters.consumption_price, consumption_value, OrderType.Buy, t, parameters
                    )
                    orders.append(bid_output)
                    buy_submitted_volume.sum_value_at(t, abs(consumption_value))

                elif abs(consumption_value) > parameters.allowed_round_off_error:
                    bid_output = self.build_offer(equipment, 0.0, consumption_value, OrderType.Sell, t, parameters)
                    orders.append(bid_output)
                    sell_submitted_volume.sum_value_at(t, abs(consumption_value))

        return orders, []

    def build_offer(
        self,
        equipment: LoadIDO,
        price: float,
        qmax: float,
        order_type: OrderType,
        time: DateTime,
        parameters: IntradayOrdersParameters,
    ) -> Order:
        bid_name = f"{order_type.value}_IDOrder_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}_{equipment.name}_{time.format('YYYY_MM_DD_HH_mm_ss')}"
        return build_intraday_order(equipment, bid_name, price, 0.0, qmax, order_type, time, parameters)
