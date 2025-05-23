"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from typing import Any

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import input_dataset_type_var, output_dataset_type_var
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.abstract_class.abstract_parameters import module_parameters_type_var
from atlas.modules.day_ahead_orders.day_ahead_orders_input_dataset import DayAheadOrdersInputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_output_dataset import DayAheadOrdersOutputDataset
from atlas.modules.day_ahead_orders.day_ahead_orders_parameters import DayAheadOrdersParameters


class DayAheadOrdersModule(
    AbstractModule[DayAheadOrdersParameters, DayAheadOrdersInputDataset, DayAheadOrdersOutputDataset]
):
    def create_parameters(self, raw_params: dict[str, Any]) -> module_parameters_type_var:
        """Creates a concrete parameters object from raw dictionary."""
        return DayAheadOrdersParameters(**raw_params)

    def import_data(
        self, raw_data: dict[str, list[BusinessModel]], parameters: module_parameters_type_var
    ) -> input_dataset_type_var:
        """Imports data using business objects and parameters."""
        return DayAheadOrdersInputDataset(raw_data, parameters)

    def validate_data(self, parameters: module_parameters_type_var, input_dataset: input_dataset_type_var) -> bool:
        """Validates imported or generated data."""
        pass

    def validates_results(
        self,
        parameters: module_parameters_type_var,
        input_dataset: input_dataset_type_var,
        output_dataset: output_dataset_type_var,
    ) -> bool:
        """Validates results"""
        pass

    def export_results(
        self,
        parameters: module_parameters_type_var,
        input_dataset: input_dataset_type_var,
        output_dataset: output_dataset_type_var,
    ) -> None:
        """Exports results."""
        pass

    def execute(
        self, parameters: module_parameters_type_var, input_dataset: input_dataset_type_var
    ) -> output_dataset_type_var:
        """Executes the module's main logic."""

    pass
