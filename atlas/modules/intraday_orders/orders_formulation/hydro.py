"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum
from pendulum import DateTime

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

        # Each fragment captures a slice of total capacity with its own price delta.
        # Fragments are sorted by price at formulation time so the cheapest capacity is offered first.
        fragment_specs = list(zip(equipment.fragment_volumes, equipment.fragment_prices, strict=True))

        # Determine the current reservoir energy level to interpolate the marginal value curve.
        forecast_horizon: DateTime = parameters.temporal.start_date - parameters.temporal.timestep
        if equipment.stored_energy is not None:
            energy_forecast = equipment.stored_energy.get_forecast(
                parameters.temporal.execution_date,
                forecast_horizon,
                forecast_horizon,
            )
            energy_level = (
                energy_forecast.get_value(forecast_horizon)
                if len(energy_forecast) > 0
                else equipment.initial_level.get_value(parameters.temporal.start_date)
            )
        else:
            energy_level = equipment.initial_level.get_value(parameters.temporal.start_date)

        # Find the two marginal-value curve points bracketing the current energy level
        # for linear interpolation of the water value.
        levels_below = [x for x in equipment.storage_marginal_value.index if int(x) <= energy_level]
        levels_above = [x for x in equipment.storage_marginal_value.index if int(x) > energy_level]

        if levels_below:
            level_inf = max(levels_below, key=lambda x: int(x))
            marginal_value_lower = equipment.storage_marginal_value.select(level_inf).upsample(
                frequency=pendulum.Duration(hours=1)
            )
        if levels_above:
            level_sup = min(levels_above, key=lambda x: int(x))
            marginal_value_upper = equipment.storage_marginal_value.select(level_sup).upsample(
                frequency=pendulum.Duration(hours=1)
            )
        if levels_below and levels_above:
            weight_lower = (int(level_sup) - energy_level) / (int(level_sup) - int(level_inf))
            weight_upper = (energy_level - int(level_inf)) / (int(level_sup) - int(level_inf))

        cleared_position = engaged_quantity(equipment, parameters)

        for i, t in enumerate(orders_timestamps):
            capacity = equipment.maximum_power.get_value(t)

            # Scale fragment volumes to actual capacity and drop fragments too small to be meaningful.
            volumes = {k: capacity * vol_frac for k, (vol_frac, _) in enumerate(fragment_specs)}
            normal_volumes = {k: v for k, v in volumes.items() if v >= parameters.hydraulic_minimal_fragment_size}
            minor_volumes = {k: v for k, v in volumes.items() if v < parameters.hydraulic_minimal_fragment_size}

            if sum(minor_volumes.values()) > 0:
                # Redistribute dropped fragment capacity proportionally among the remaining fragments.
                reduced_capacity = sum(normal_volumes.values())
                volumes = {k: capacity * v / reduced_capacity for k, v in normal_volumes.items()}

            # Compute water value at current energy level via interpolation.
            volume_prices = []
            for k, v in volumes.items():
                _, price_delta = fragment_specs[k]
                if not levels_below:
                    price = marginal_value_upper.get_value(t) + price_delta
                elif not levels_above:
                    price = marginal_value_lower.get_value(t) + price_delta
                else:
                    water_value = weight_lower * marginal_value_lower.get_value(
                        t
                    ) + weight_upper * marginal_value_upper.get_value(t)
                    price = water_value + price_delta
                volume_prices.append((v, price))

            volume_prices.sort(key=lambda x: x[1])

            # Walk through fragments from cheapest to most expensive.
            # remaining_engagement tracks how much of the cleared engagement is still "above" us:
            # > 0 → still within the buy zone (need to acquire more than we've sold)
            # straddling 0 → this fragment crosses the engagement boundary (split buy/sell)
            # < 0 → past the engagement boundary (into the sell zone)
            remaining_engagement = cleared_position.get_value(t)

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
