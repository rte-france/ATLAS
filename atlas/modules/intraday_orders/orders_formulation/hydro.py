"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas.common.optimal_dispatch.marginal_pricing import InterpolatedMarginalValue
from atlas.enums import OrderType
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.input_objects.hydro import HydroIDO
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import build_intraday_order, engaged_quantity
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


class HydroOrdersFormulator(AbstractOrdersFormulator[HydroIDO]):
    EQUIPMENT_TYPE_NAME = "hydraulic"

    def formulate_equipment_orders(
        self,
        equipment: HydroIDO,
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling], Timeseries, Timeseries]:
        orders: list[Order] = []
        sell_values: list[float] = [0.0] * len(orders_timestamps)
        buy_values: list[float] = [0.0] * len(orders_timestamps)

        marginal_value = InterpolatedMarginalValue.for_unit(
            equipment,
            parameters.temporal.execution_date,
            parameters.temporal.start_date - parameters.temporal.timestep,
        )

        cleared_engagement = engaged_quantity(equipment, parameters)

        for i, t in enumerate(orders_timestamps):
            capacity = equipment.maximum_power.get_value(t)
            volumes = equipment.bid_volumes(capacity, parameters.hydraulic_minimal_fragment_size)

            # Offer the cheapest capacity first.
            water_value = marginal_value.value_at(t)
            volume_prices = [(v, water_value + equipment.fragment_data[k].price) for k, v in volumes.items()]
            volume_prices.sort(key=lambda x: x[1])

            # Walk through fragments from cheapest to most expensive.
            # remaining_engagement tracks how much of the cleared engagement is still "above" us:
            # > 0 → still within the buy zone (need to acquire more than we've sold)
            # straddling 0 → this fragment crosses the engagement boundary (split buy/sell)
            # < 0 → past the engagement boundary (into the sell zone)
            remaining_engagement = cleared_engagement.get_value(t)

            for fragment_idx, (volume, price) in enumerate(volume_prices, start=1):
                remaining_engagement -= volume

                if remaining_engagement > 0:
                    order = self._build_offer(volume, price, OrderType.Buy, equipment, t, fragment_idx, parameters)
                    if order is not None:
                        orders.append(order)
                        buy_values[i] += abs(volume)

                elif remaining_engagement < 0 and abs(remaining_engagement) < volume:
                    # Fragment straddles the engagement boundary: split into buy and sell parts.
                    buy_volume = volume + remaining_engagement
                    sell_volume = abs(remaining_engagement)
                    for frag_volume, frag_type in ((buy_volume, OrderType.Buy), (sell_volume, OrderType.Sell)):
                        order = self._build_offer(frag_volume, price, frag_type, equipment, t, fragment_idx, parameters)
                        if order is not None:
                            orders.append(order)
                            if frag_type == OrderType.Buy:
                                buy_values[i] += abs(frag_volume)
                            else:
                                sell_values[i] += abs(frag_volume)

                elif remaining_engagement < 0 and abs(remaining_engagement) > volume:
                    order = self._build_offer(volume, price, OrderType.Sell, equipment, t, fragment_idx, parameters)
                    if order is not None:
                        orders.append(order)
                        sell_values[i] += abs(volume)

        sell_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, sell_values
        )
        buy_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, buy_values
        )
        return orders, [], sell_submitted_volume, buy_submitted_volume

    def _build_offer(
        self,
        volume: float,
        price: float,
        order_type: OrderType,
        equipment: HydroIDO,
        time: DateTime,
        fragment_idx: int,
        parameters: IntradayOrdersParameters,
    ) -> Order | None:
        if volume <= parameters.allowed_round_off_error:
            return None
        bid_name = f"id_hydraulic_{order_type.value.lower()}_fragment_{fragment_idx}_at_{time.format('DD_MM_YYYY_HH_mm_ss')}_for_unit_{equipment.name}_{parameters.temporal.execution_date.format('DD_MM_YYYY_HH_mm_ss')}"
        return build_intraday_order(equipment, bid_name, price, 0.0, volume, order_type, time, parameters)
