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
from atlas.modules.intraday_orders.utils import build_intraday_order
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling


class HydroOrdersFormulator(AbstractOrdersFormulator[HydroIDO]):
    EQUIPMENT_TYPE_NAME = "hydraulic"

    def formulate_equipment_orders(
        self,
        equipment: HydroIDO,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling]]:
        orders: list[Order] = []

        delta_wu: dict[float, tuple[float, float]] = {}
        for category in range(len(equipment.fragment_volumes)):
            delta_wu[category] = (equipment.fragment_volumes[category], equipment.fragment_prices[category])

        forecast_horizon: DateTime = parameters.temporal.start_date - parameters.temporal.timestep

        if equipment.stored_energy is not None:
            energy_forecast = equipment.stored_energy.get_forecast(
                parameters.temporal.execution_date,
                forecast_horizon,
                forecast_horizon,
            )
            if len(energy_forecast) > 0:
                energy_level = energy_forecast.get_value(forecast_horizon)
            else:
                energy_level = equipment.initial_level.get_value(parameters.temporal.start_date)
        else:
            energy_level = equipment.initial_level.get_value(parameters.temporal.start_date)

        xmin = filter(lambda x: int(x) <= energy_level, equipment.storage_marginal_value.index)
        xmax = filter(lambda x: int(x) > energy_level, equipment.storage_marginal_value.index)

        if xmin:
            xpmin = max(xmin, key=lambda x: int(x))
            level_inf = equipment.storage_marginal_value.select(xpmin).upsample(frequency=pendulum.Duration(hours=1))
        if xmax:
            xpmax = min(xmax, key=lambda x: int(x))
            level_sup = equipment.storage_marginal_value.select(xpmax).upsample(frequency=pendulum.Duration(hours=1))
        if xmin and xmax:
            weight_inf = (int(xpmax) - energy_level) / (int(xpmax) - int(xpmin))
            weight_sup = (energy_level - int(xpmin)) / (int(xpmax) - int(xpmin))

        for t in orders_timestamps:
            capacity = equipment.maximum_power.get_value(t)
            volumes = {key: capacity * vu[0] for key, vu in delta_wu.items()}

            normal_volumes = {key: v for key, v in volumes.items() if v >= parameters.hydraulic_minimal_fragment_size}
            minor_volumes = {key: v for key, v in volumes.items() if v < parameters.hydraulic_minimal_fragment_size}

            if sum(minor_volumes.values()) > 0:
                reduced_capacity = sum(normal_volumes.values())
                volumes = {key: capacity * v / reduced_capacity for (key, v) in normal_volumes.items()}

            volume_prices = []
            for k, v in volumes.items():
                if not xmin:
                    price = level_sup.get_value(t) + delta_wu[k][1]
                elif not xmax:
                    price = level_inf.get_value(t) + delta_wu[k][1]
                else:
                    pmin = level_inf.get_value(t)
                    pmax = level_sup.get_value(t)
                    price = weight_inf * pmin + weight_sup * pmax + delta_wu[k][1]
                volume_prices.append((v, price))

            volume_prices.sort(key=lambda x: x[1])
            volume_engagement = equipment.da_cleared_quantity.get_value(
                t
            ) + equipment.total_id_cleared_quantity.get_value(t)

            for volume, price in volume_prices:
                volume_engagement -= volume

                if volume_engagement > 0:
                    order = self.build_offer(volume, price, OrderType.Buy, equipment, t, parameters)
                    if order is not None:
                        orders.append(order)
                        buy_submitted_volume.sum_value_at(t, abs(volume))

                elif volume_engagement < 0 and abs(volume_engagement) < volume:
                    order = self.build_offer(volume + volume_engagement, price, OrderType.Buy, equipment, t, parameters)
                    if order is not None:
                        orders.append(order)
                        buy_submitted_volume.sum_value_at(t, abs(volume + volume_engagement))
                    order = self.build_offer(abs(volume_engagement), price, OrderType.Sell, equipment, t, parameters)
                    if order is not None:
                        orders.append(order)
                        sell_submitted_volume.sum_value_at(t, abs(volume))

                elif volume_engagement < 0 and abs(volume_engagement) > volume:
                    order = self.build_offer(volume, price, OrderType.Sell, equipment, t, parameters)
                    if order is not None:
                        orders.append(order)
                        sell_submitted_volume.sum_value_at(t, abs(volume))

        return orders, []

    def build_offer(
        self,
        volume: float,
        price: float,
        order_type: OrderType,
        equipment: HydroIDO,
        time: DateTime,
        parameters: IntradayOrdersParameters,
    ) -> Order | None:
        if volume <= parameters.allowed_round_off_error:
            return None
        bid_name = f"ID_hydraulic_{order_type}_fragment_{str(volume)}_at_{time.format('YYYY_MM_DD_HH_mm_ss')}_for_unit_{equipment.name}_{parameters.temporal.execution_date.format('YYYY_MM_DD_HH_mm_ss')}"
        return build_intraday_order(equipment, bid_name, price, 0.0, volume, order_type, time, parameters)
