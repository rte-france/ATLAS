"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

import atlas.config as cfg
from atlas.enums import OrderType
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.input_objects.storage import StorageIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order, engaged_quantity
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


def compute_initial_prices(
    equipment: StorageIDO, orders_timestamps: list[DateTime], parameters: IntradayOrdersParameters
) -> tuple[float, float]:
    min_sell_price = 9999.0
    max_buy_price = 0.0

    if equipment.portfolio.market_area.id_price_forecast is None:
        return min_sell_price, max_buy_price

    price_forecast = equipment.portfolio.market_area.id_price_forecast.get_forecast(
        parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
    )

    new_planning = equipment.id_po_for_orders.get_forecast(
        parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
    )
    previous_planning = engaged_quantity(equipment, parameters)

    qo = new_planning - previous_planning

    time_sell = []
    time_buy = []

    p_v = []
    p_a = []

    # Check whether to create sell or buy orders and store the time stamp of these orders
    for t in orders_timestamps:
        if qo.get_value(t) > parameters.allowed_round_off_error:
            time_sell.append(t)

        elif qo.get_value(t) < -parameters.allowed_round_off_error:
            time_buy.append(t)

    # Store the corresponding prices
    for t in time_sell:
        p_v.append(price_forecast.get_value(t))

    for t in time_buy:
        p_a.append(price_forecast.get_value(t))

    if p_v:
        min_sell_price = min(p_v)
    if p_a:
        max_buy_price = max(p_a)

    # Special cases:
    if not time_sell or min_sell_price < 0:
        # In this case, we plan to buy without selling or there is negative sell price, we set sell price to 0
        final_buy_price = max_buy_price
        final_sell_price = 0.0

    # QB: This check seems incorrect as it drives prices down if storage are marginal in buy orders with null price.
    # If Buy price are always null and sell price are not, we want to enter the third case
    # elif BuyPrice_max==0: #in this case, there is only sell orders or buy price are always null
    elif not time_buy:
        final_sell_price = min_sell_price
        final_buy_price = 0.0

    # Safeguard to prevent division error, however this case should not happen if efficiencies are not both equal to 1
    elif min_sell_price == 0.0 and max_buy_price == 0.0:
        final_sell_price = 0.0
        final_buy_price = 0.0
        cfg.logger.warning(
            f"Price calculation for unit {equipment.name} resulted in both buying and selling prices being equal to 0"
        )

    else:
        a = (equipment.discharge_efficiency * equipment.charge_efficiency * min_sell_price - max_buy_price) / (
            equipment.discharge_efficiency * equipment.charge_efficiency * min_sell_price + max_buy_price
        )
        final_sell_price = min_sell_price * (1.0 - a)
        final_buy_price = max_buy_price * (1.0 + a)

    return final_sell_price, final_buy_price


class StorageOrdersFormulator(AbstractOrdersFormulator[StorageIDO]):
    EQUIPMENT_TYPE_NAME = "storage"

    def formulate_equipment_orders(
        self,
        equipment: StorageIDO,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling]]:
        final_sell_price, final_buy_price = compute_initial_prices(equipment, orders_timestamps, parameters)

        new_planning = equipment.id_po_for_orders.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
        )
        previous_planning = engaged_quantity(equipment, parameters)

        cfg.logger.info(f"Formulating storage orders for unit {equipment.name}")

        orders: list[Order] = []
        couplings: list[OrderCoupling] = []
        daily_buy_quantity = 0.0
        daily_sell_quantity = 0.0

        for t in orders_timestamps:
            # Read new and previous planning at this time step
            previous_quantity = previous_planning.get_value(t)
            new_quantity = new_planning.get_value(t)

            if new_quantity > previous_quantity:
                q_order = new_quantity - previous_quantity
                price = final_sell_price
                order_type = OrderType.Sell
                sell_submitted_volume.sum_value_at(t, q_order)
                daily_sell_quantity += sell_submitted_volume.get_value(t)

            elif previous_quantity > new_quantity:
                q_order = previous_quantity - new_quantity
                price = final_buy_price
                order_type = OrderType.Buy
                buy_submitted_volume.sum_value_at(t, q_order)
                daily_buy_quantity += buy_submitted_volume.get_value(t)

            else:
                continue

            if q_order > parameters.allowed_round_off_error:
                order_name = f"id_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}_{equipment.name}_{t.format('DD_MM_YYYY_HH_mm_ss')}"
                order = build_intraday_order(
                    equipment, order_name, price, 0.0, q_order, order_type, t, parameters, is_agent_tso=None
                )
                orders.append(order)

        return orders, couplings
