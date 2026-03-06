"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import AtlasDataset
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.modules.intraday_orders.input_dataset import IntradayOrdersInputDataset
from atlas.modules.intraday_orders.orders_formulation.hydro_orders_formulator import HydroOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.load_orders_formulator import LoadOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.non_dispatchable_orders_formulator import (
    NonDispatchableOrdersFormulator,
)
from atlas.modules.intraday_orders.orders_formulation.solar_orders_formulator import SolarOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.storage_orders_formulator import StorageOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.thermal_orders_formulator import ThermalOrdersFormulator
from atlas.modules.intraday_orders.orders_formulation.wind_orders_formulator import WindOrdersFormulator
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters
from atlas.modules.intraday_orders.utils import get_orders_timestamps


class IntradayOrdersModule(
    AbstractModule[IntradayOrdersParameters, IntradayOrdersInputDataset, IntradayOrdersOutputDataset]
):
    def get_parameters_class(self) -> type[IntradayOrdersParameters]:
        return IntradayOrdersParameters

    def import_data(self, raw_data: AtlasDataset, parameters: IntradayOrdersParameters) -> IntradayOrdersInputDataset:
        return IntradayOrdersInputDataset(raw_data)

    def validate_data(self, parameters: IntradayOrdersParameters, input_dataset: IntradayOrdersInputDataset) -> bool:
        # TODO: ask POs if something is required here
        return True

    def execute(
        self, parameters: IntradayOrdersParameters, input_dataset: IntradayOrdersInputDataset
    ) -> IntradayOrdersOutputDataset:
        dataset = IntradayOrdersOutputDataset()
        orders_timestamps = get_orders_timestamps(parameters.start_date, parameters.end_date, parameters.timestep)
        HydroOrdersFormulator().formulate_orders(input_dataset.hydro, orders_timestamps, dataset, parameters)
        LoadOrdersFormulator().formulate_orders(input_dataset.load, orders_timestamps, dataset, parameters)
        NonDispatchableOrdersFormulator().formulate_orders(
            input_dataset.other_non_dispatchable, orders_timestamps, dataset, parameters
        )
        SolarOrdersFormulator().formulate_orders(input_dataset.solar, orders_timestamps, dataset, parameters)
        StorageOrdersFormulator().formulate_orders(input_dataset.storage, orders_timestamps, dataset, parameters)
        ThermalOrdersFormulator().formulate_orders(input_dataset.thermal, orders_timestamps, dataset, parameters)
        WindOrdersFormulator().formulate_orders(input_dataset.wind, orders_timestamps, dataset, parameters)
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
