"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import atlas.config as cfg
from atlas import AtlasDataset
from atlas.abstract_class.module import AbstractModule
from atlas.modules.intraday_orders.input_dataset import IntradayOrdersInputDataset
from atlas.modules.intraday_orders.orders_formulation.abstract_orders import AbstractOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.hydro import HydroOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.load import LoadOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.non_dispatchable import (
    NonDispatchableOrdersFormulator,
)
from atlas.modules.intraday_orders.orders_formulation.solar import SolarOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.storage import StorageOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.thermal import ThermalOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.wind import WindOrdersFormulator
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.timing import generate_datetimes


class IntradayOrdersModule(
    AbstractModule[IntradayOrdersParameters, IntradayOrdersInputDataset, IntradayOrdersOutputDataset]
):
    def get_parameters_class(self) -> type[IntradayOrdersParameters]:
        return IntradayOrdersParameters

    def import_data(self, input_data: AtlasDataset, parameters: IntradayOrdersParameters) -> IntradayOrdersInputDataset:
        return IntradayOrdersInputDataset(input_data.set_frequency_all(parameters.temporal.timestep, inplace=True))

    def validate_data(self, parameters: IntradayOrdersParameters, input_dataset: IntradayOrdersInputDataset) -> bool:
        # TODO: ask POs if something is required here
        return True

    def execute(
        self, parameters: IntradayOrdersParameters, input_dataset: IntradayOrdersInputDataset
    ) -> IntradayOrdersOutputDataset:
        cfg.logger.info("Initialization of the Intraday Orders module...")
        dataset = IntradayOrdersOutputDataset(input_dataset)
        orders_timestamps = generate_datetimes(
            parameters.temporal.start_date, parameters.penultimate_date, parameters.temporal.timestep
        )

        if len(orders_timestamps) == 0:
            cfg.logger.warning("The time window to formulate orders is empty.")
            return dataset

        formulators: list[tuple[str, AbstractOrdersFormulator, list]] = [
            ("hydro", HydroOrdersFormulator(), input_dataset.hydro),
            ("load", LoadOrdersFormulator(), input_dataset.load),
            ("non-dispatchable", NonDispatchableOrdersFormulator(), input_dataset.other_non_dispatchable),
            ("solar", SolarOrdersFormulator(), input_dataset.solar),
            ("storage", StorageOrdersFormulator(), input_dataset.storage),
            ("thermal", ThermalOrdersFormulator(), input_dataset.thermal),
            ("wind", WindOrdersFormulator(), input_dataset.wind),
        ]

        for _name, formulator, equipments in formulators:
            result = formulator.formulate(equipments, orders_timestamps, parameters)
            dataset.order.extend(result.orders)
            dataset.order_coupling.extend(result.order_couplings)

        cfg.logger.info("Formulation of intraday orders successfully completed.")
        return dataset

    def validates_results(
        self,
        parameters: IntradayOrdersParameters,
        input_dataset: IntradayOrdersInputDataset,
        output_dataset: IntradayOrdersOutputDataset,
    ) -> bool:
        return True

    def export_results(
        self,
        parameters: IntradayOrdersParameters,
        input_dataset: IntradayOrdersInputDataset,
        output_dataset: IntradayOrdersOutputDataset,
    ) -> None:
        pass
