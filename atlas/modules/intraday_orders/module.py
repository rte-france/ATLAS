"""
Copyright (c) 2026, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas import BusinessModel
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.modules.intraday_orders.input_dataset import IntradayOrdersInputDataset
from atlas.modules.intraday_orders.output_dataset import IntradayOrdersOutputDataset
from atlas.modules.intraday_orders.parameters import IntradayOrdersParameters


class IntradayOrdersModule(
    AbstractModule[IntradayOrdersParameters, IntradayOrdersInputDataset, IntradayOrdersOutputDataset]
):
    def get_parameters_class(self) -> type[IntradayOrdersParameters]:
        return IntradayOrdersParameters

    def import_data(
        self, raw_data: dict[str, list[type[BusinessModel]]], parameters: IntradayOrdersParameters
    ) -> IntradayOrdersInputDataset:
        pass

    def validate_data(self, parameters: IntradayOrdersParameters, input_dataset: IntradayOrdersInputDataset) -> bool:
        pass

    def execute(
        self, parameters: IntradayOrdersParameters, input_dataset: IntradayOrdersInputDataset
    ) -> IntradayOrdersOutputDataset:
        return IntradayOrdersOutputDataset()

    def validates_results(
        self,
        parameters: IntradayOrdersParameters,
        input_dataset: IntradayOrdersInputDataset,
        output_dataset: IntradayOrdersOutputDataset,
    ) -> bool:
        return False

    def export_results(
        self,
        parameters: IntradayOrdersParameters,
        input_dataset: IntradayOrdersInputDataset,
        output_dataset: IntradayOrdersOutputDataset,
    ) -> None:
        pass
