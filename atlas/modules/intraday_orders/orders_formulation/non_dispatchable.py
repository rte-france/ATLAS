"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas import Order, OrderCoupling, Timeseries
from atlas.enums import OrderType
from atlas.modules.intraday_orders.input_objects.other_non_dispatchable import OtherNonDispatchableIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order


class NonDispatchableOrdersFormulator(AbstractOrdersFormulator[OtherNonDispatchableIDO]):
    EQUIPMENT_TYPE_NAME = "non-dispatchable"

    def formulate_equipment_orders(
        self,
        equipment: OtherNonDispatchableIDO,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling]]:
        orders: list[Order] = []

        production_new_planing = equipment.maximum_power_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
        )
        production_engagement = equipment.da_cleared_quantity + equipment.total_id_cleared_quantity
        production_forecast = production_new_planing - production_engagement

        variable_costs = None
        if equipment.variable_cost is not None:
            variable_costs = equipment.variable_cost.filter(item=orders_timestamps, inplace=False)

        if equipment.portfolio.market_area.id_price_forecast is None:
            return orders, []

        price_forecast = equipment.portfolio.market_area.id_price_forecast.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.temporal.end_date
        )

        for t in orders_timestamps:
            bid_name = f"otherND_IDOrder_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}_{equipment.name}_{t.format('YYYY_MM_DD_HH_mm_ss')}"
            production_value = production_forecast.get_value(t)
            buy_isp_forecast = price_forecast.get_value(t) * (1.0 + parameters.large_imbalance_penalty)

            if abs(production_value) <= parameters.allowed_round_off_error:
                continue

            if production_value > 0:
                order_type = OrderType.Sell
                price = variable_costs.get_value(t)
                sell_submitted_volume.sum_value_at(t, abs(production_value))
            else:
                order_type = OrderType.Buy
                price = variable_costs.get_value(t) + buy_isp_forecast
                buy_submitted_volume.sum_value_at(t, abs(production_value))

            orders.append(
                build_intraday_order(equipment, bid_name, price, 0.0, abs(production_value), order_type, t, parameters)
            )

        return orders, []
