"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from abc import ABC
from typing import Generic, TypeVar

from pendulum import DateTime

import atlas.config as cfg
from atlas import Equipment, Timeseries
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters

E = TypeVar("E", bound=Equipment)


class AbstractOrdersFormulator(ABC, Generic[E]):
    EQUIPMENT_TYPE_NAME: str

    def formulate(
        self,
        equipments: list[E],
        orders_timestamps: list[DateTime],
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        message = f"Formulation of the intraday {self.EQUIPMENT_TYPE_NAME} orders"
        cfg.logger.info(f"{message} [start]")
        for equipment in equipments:
            self.process_equipment(equipment, orders_timestamps, dataset, parameters)
        cfg.logger.info(f"{message} [end]")

    def process_equipment(
        self,
        equipment: E,
        orders_timestamps: list[DateTime],
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        sell_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0
        )
        buy_submitted_volume = Timeseries.from_index(
            parameters.temporal.start_date, parameters.temporal.timestep, parameters.penultimate_date, 0
        )

        self.formulate_equipment_orders(
            equipment, orders_timestamps, buy_submitted_volume, sell_submitted_volume, dataset, parameters
        )

        equipment.id_buy_submitted_volume.add(buy_submitted_volume, parameters.temporal.execution_date)
        equipment.id_sell_submitted_volume.add(sell_submitted_volume, parameters.temporal.execution_date)

        equipment.total_id_buy_submitted_volume += buy_submitted_volume
        equipment.total_id_sell_submitted_volume += sell_submitted_volume

    def formulate_equipment_orders(
        self,
        equipment: E,
        orders_timestamps: list[DateTime],
        buy_submitted_volume: Timeseries,
        sell_submitted_volume: Timeseries,
        dataset: IntradayOrdersOutputDataset,
        parameters: IntradayOrdersParameters,
    ):
        raise NotImplementedError()
