"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas.enums import OrderType
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.input_objects.other_non_dispatchable import OtherNonDispatchableIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order, engaged_quantity
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


class NonDispatchableOrdersFormulator(AbstractOrdersFormulator[OtherNonDispatchableIDO]):
    EQUIPMENT_TYPE_NAME = "non-dispatchable"

    def formulate_equipment_orders(
        self,
        equipment: OtherNonDispatchableIDO,
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling], Timeseries, Timeseries]:
        orders: list[Order] = []
        sell_values: list[float] = [0.0] * len(orders_timestamps)
        buy_values: list[float] = [0.0] * len(orders_timestamps)

        target_planning = equipment.maximum_power_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
        )
        cleared_engagement = engaged_quantity(equipment, parameters)
        production_delta = target_planning - cleared_engagement

        variable_costs = None
        if equipment.variable_cost is not None:
            variable_costs = equipment.variable_cost.filter(item=orders_timestamps, inplace=False)

        if equipment.portfolio.market_area.id_price_forecast is None:
            zero = Timeseries.from_index(
                parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0.0
            )
            return orders, [], zero, zero

        price_forecast = equipment.portfolio.market_area.id_price_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
        )

        for i, t in enumerate(orders_timestamps):
            bid_name = f"other_nd_id_order_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}_{equipment.name}_{t.format('DD_MM_YYYY_HH_mm_ss')}"
            production_value = production_delta.get_value(t)
            buy_isp_forecast = price_forecast.get_value(t) * (1.0 + parameters.large_imbalance_penalty)

            if abs(production_value) <= parameters.allowed_round_off_error:
                continue

            if production_value > 0:
                order_type = OrderType.Sell
                price = variable_costs.get_value(t)
                sell_values[i] += abs(production_value)
            else:
                order_type = OrderType.Buy
                price = variable_costs.get_value(t) + buy_isp_forecast
                buy_values[i] += abs(production_value)

            orders.append(
                build_intraday_order(equipment, bid_name, price, 0.0, abs(production_value), order_type, t, parameters)
            )

        sell_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, sell_values
        )
        buy_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, buy_values
        )
        return orders, [], sell_submitted_volume, buy_submitted_volume
