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


def compute_efficiency_adjusted_prices(
    equipment: StorageIDO, orders_timestamps: list[DateTime], parameters: IntradayOrdersParameters
) -> tuple[float, float]:
    """Compute sell and buy prices adjusted for round-trip storage efficiency.

    A storage unit must sell high enough and buy low enough to remain profitable given
    the combined charge/discharge efficiency loss.  The adjustment coefficient ``a`` is
    derived from the ratio of efficiency-weighted minimum sell price to maximum buy price:
    the further apart sell and buy prices are, the smaller ``a`` becomes, compressing both
    prices toward the market midpoint.

    :return: ``(sell_price, buy_price)`` to use for all orders in this session.
    """
    min_sell_price = float("inf")
    max_buy_price = 0.0

    # The caller guarantees a price forecast exists; asserted here so a None can never
    # silently produce orders priced at +inf.
    assert equipment.portfolio.market_area.id_price_forecast is not None

    price_forecast = equipment.portfolio.market_area.id_price_forecast.get_forecast(
        parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
    )

    target_planning = equipment.id_po_for_orders.get_forecast(
        parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
    )
    cleared_engagement = engaged_quantity(equipment, parameters)
    planning_delta = target_planning - cleared_engagement

    sell_timestamps: list[DateTime] = []
    buy_timestamps: list[DateTime] = []
    for t in orders_timestamps:
        delta = planning_delta.get_value(t)
        if delta > parameters.allowed_round_off_error:
            sell_timestamps.append(t)
        elif delta < -parameters.allowed_round_off_error:
            buy_timestamps.append(t)

    sell_side_prices = [price_forecast.get_value(t) for t in sell_timestamps]
    buy_side_prices = [price_forecast.get_value(t) for t in buy_timestamps]

    if sell_side_prices:
        min_sell_price = min(sell_side_prices)
    if buy_side_prices:
        max_buy_price = max(buy_side_prices)

    # Special cases where the standard efficiency formula cannot be applied:
    if not sell_timestamps or min_sell_price < 0:
        # No sell periods or negative sell price: only buy orders, no efficiency adjustment needed.
        return 0.0, max_buy_price

    if not buy_timestamps:
        # Only sell orders: no efficiency adjustment needed.
        return min_sell_price, 0.0

    # Safeguard: both prices zero would cause division by zero in the formula below.
    if min_sell_price == 0.0 and max_buy_price == 0.0:
        cfg.logger.warning(
            f"Price calculation for unit {equipment.name} resulted in both buying and selling prices being equal to 0"
        )
        return 0.0, 0.0

    # Round-trip efficiency adjustment: sell price is raised and buy price is lowered symmetrically
    # so that a full charge-discharge cycle remains profitable after efficiency losses (η_d × η_c).
    round_trip_efficiency = equipment.discharge_efficiency * equipment.charge_efficiency
    spread_compression = (round_trip_efficiency * min_sell_price - max_buy_price) / (
        round_trip_efficiency * min_sell_price + max_buy_price
    )
    return min_sell_price * (1.0 - spread_compression), max_buy_price * (1.0 + spread_compression)


class StorageOrdersFormulator(AbstractOrdersFormulator[StorageIDO]):
    EQUIPMENT_TYPE_NAME = "storage"

    def formulate_equipment_orders(
        self,
        equipment: StorageIDO,
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling], Timeseries, Timeseries]:
        if equipment.portfolio.market_area.id_price_forecast is None:
            zero = Timeseries.from_index(
                parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0.0
            )
            return [], [], zero, zero

        sell_price, buy_price = compute_efficiency_adjusted_prices(equipment, orders_timestamps, parameters)

        target_planning = equipment.id_po_for_orders.get_forecast(
            parameters.temporal.execution_date, parameters.temporal.start_date, parameters.penultimate_date
        )
        cleared_engagement = engaged_quantity(equipment, parameters)

        orders: list[Order] = []
        couplings: list[OrderCoupling] = []
        sell_values: list[float] = [0.0] * len(orders_timestamps)
        buy_values: list[float] = [0.0] * len(orders_timestamps)

        for i, t in enumerate(orders_timestamps):
            cleared_quantity = cleared_engagement.get_value(t)
            target_quantity = target_planning.get_value(t)

            if target_quantity > cleared_quantity:
                q_order = target_quantity - cleared_quantity
                price = sell_price
                order_type = OrderType.Sell
                sell_values[i] += q_order

            elif cleared_quantity > target_quantity:
                q_order = cleared_quantity - target_quantity
                price = buy_price
                order_type = OrderType.Buy
                buy_values[i] += q_order

            else:
                continue

            if q_order > parameters.allowed_round_off_error:
                order_name = f"id_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}_{equipment.name}_{t.format('DD_MM_YYYY_HH_mm_ss')}"
                order = build_intraday_order(
                    equipment, order_name, price, 0.0, q_order, order_type, t, parameters, is_agent_tso=None
                )
                orders.append(order)

        sell_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, sell_values
        )
        buy_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, buy_values
        )
        return orders, couplings, sell_submitted_volume, buy_submitted_volume
