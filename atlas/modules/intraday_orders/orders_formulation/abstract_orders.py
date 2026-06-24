"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from abc import ABC
from dataclasses import dataclass, field
from typing import TypeVar

from pendulum import DateTime

import atlas.config as cfg
from atlas.math.timeseries import Timeseries
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.objects.equipment.equipment import Equipment
from atlas.objects.market.order import Order
from atlas.objects.market.order_coupling import OrderCoupling

E = TypeVar("E", bound=Equipment)


@dataclass
class FormulatorResult:
    orders: list[Order] = field(default_factory=list)
    order_couplings: list[OrderCoupling] = field(default_factory=list)


class AbstractOrdersFormulator[E](ABC):
    EQUIPMENT_TYPE_NAME: str

    def formulate(
        self,
        equipments: list[E],
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> FormulatorResult:
        result = FormulatorResult()
        message = f"Formulation of the intraday {self.EQUIPMENT_TYPE_NAME} orders"
        cfg.logger.info(f"{message} [start]")
        for equipment in equipments:
            orders, couplings = self.process_equipment(equipment, orders_timestamps, parameters)
            result.orders.extend(orders)
            result.order_couplings.extend(couplings)
        cfg.logger.info(f"{message} [end]")
        return result

    def process_equipment(
        self,
        equipment: E,
        orders_timestamps: list[DateTime],
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling]]:
        sell_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0
        )
        buy_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0
        )

        orders, couplings = self.formulate_equipment_orders(
            equipment, orders_timestamps, buy_submitted_volume, sell_submitted_volume, parameters
        )
        if equipment.id_buy_submitted_volume and equipment.id_sell_submitted_volume:
            equipment.id_buy_submitted_volume.add(buy_submitted_volume, parameters.temporal.execution_date)
            equipment.id_sell_submitted_volume.add(sell_submitted_volume, parameters.temporal.execution_date)

        # total_id_*_submitted_volume is None until the first intraday session accumulates onto it
        equipment.total_id_buy_submitted_volume = (
            buy_submitted_volume
            if equipment.total_id_buy_submitted_volume is None
            else equipment.total_id_buy_submitted_volume + buy_submitted_volume
        )
        equipment.total_id_sell_submitted_volume = (
            sell_submitted_volume
            if equipment.total_id_sell_submitted_volume is None
            else equipment.total_id_sell_submitted_volume + sell_submitted_volume
        )

        return orders, couplings

    def formulate_equipment_orders(
        self,
        equipment: E,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        parameters: IntradayOrdersParameters,
    ) -> tuple[list[Order], list[OrderCoupling]]:
        raise NotImplementedError()
