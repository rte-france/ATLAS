"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pendulum import DateTime

from atlas.common.optimal_dispatch.marginal_pricing import InterpolatedMarginalValue, bid_volumes
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
            volumes = bid_volumes(equipment.fragment_data, capacity, parameters.hydraulic_minimal_fragment_size)

            # Offer the cheapest capacity first.
            water_value = marginal_value.value_at(t)
            volume_prices = [(v, water_value + equipment.fragment_data[k].price) for k, v in volumes.items()]
            volume_prices.sort(key=lambda x: x[1])

            # Walk the fragments cheapest first: the cleared engagement is bought back before
            # anything is sold, so each fragment is split where the engagement runs out.
            # A fragment entirely inside the engagement is all buy, one entirely past it all
            # sell; _build_offer drops the empty side.
            remaining_engagement = cleared_engagement.get_value(t)

            for fragment_idx, (volume, price) in enumerate(volume_prices, start=1):
                buy_volume = min(volume, max(remaining_engagement, 0.0))
                remaining_engagement -= volume

                for frag_volume, frag_type in ((buy_volume, OrderType.Buy), (volume - buy_volume, OrderType.Sell)):
                    order = self._build_offer(frag_volume, price, frag_type, equipment, t, fragment_idx, parameters)
                    if order is not None:
                        orders.append(order)
                        if frag_type == OrderType.Buy:
                            buy_values[i] += frag_volume
                        else:
                            sell_values[i] += frag_volume

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
