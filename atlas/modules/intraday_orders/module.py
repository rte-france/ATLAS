"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import AtlasDataset
from atlas.abstract_class.module import AbstractModule
from atlas.modules.intraday_orders.input_dataset import IntradayOrdersInputDataset
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
        return IntradayOrdersInputDataset(input_data)

    def validate_data(self, parameters: IntradayOrdersParameters, input_dataset: IntradayOrdersInputDataset) -> bool:
        # TODO: ask POs if something is required here
        return True

    def execute(
        self, parameters: IntradayOrdersParameters, input_dataset: IntradayOrdersInputDataset
    ) -> IntradayOrdersOutputDataset:
        dataset = IntradayOrdersOutputDataset()
        orders_timestamps = generate_datetimes(
            parameters.temporal.start_date, parameters.temporal.end_date, parameters.temporal.timestep
        )
        HydroOrdersFormulator().formulate(input_dataset.hydro, orders_timestamps, dataset, parameters)
        LoadOrdersFormulator().formulate(input_dataset.load, orders_timestamps, dataset, parameters)
        NonDispatchableOrdersFormulator().formulate(
            input_dataset.other_non_dispatchable, orders_timestamps, dataset, parameters
        )
        SolarOrdersFormulator().formulate(input_dataset.solar, orders_timestamps, dataset, parameters)
        StorageOrdersFormulator().formulate(input_dataset.storage, orders_timestamps, dataset, parameters)
        ThermalOrdersFormulator().formulate(input_dataset.thermal, orders_timestamps, dataset, parameters)
        WindOrdersFormulator().formulate(input_dataset.wind, orders_timestamps, dataset, parameters)

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
