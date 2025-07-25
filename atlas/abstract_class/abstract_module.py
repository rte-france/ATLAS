"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractModule
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import input_dataset_type_var, output_dataset_type_var
from atlas.abstract_class.abstract_parameters import module_parameters_type_var


class AbstractModule(ABC, Generic[module_parameters_type_var, input_dataset_type_var, output_dataset_type_var]):
    """Abstract base class for modules with standard execution lifecycle."""

    def before_execution(self) -> None:
        """Hook before execution."""

    def after_execution(self) -> None:
        """Hook after execution."""

    @abstractmethod
    def get_parameters_class(self) -> type[module_parameters_type_var]:
        """Returns the concrete Parameters class for this module."""

    def create_parameters(self, raw_params: dict[str, Any] | str | Path) -> module_parameters_type_var:
        """Creates a concrete parameters object from raw dictionary or file path.

        This method provides a default implementation that handles both formats:
        - If raw_params is dict: uses Parameters.model_validate(raw_params)
        - If raw_params is str/Path: uses Parameters.from_file(raw_params)
        """
        parameters_class = self.get_parameters_class()

        if isinstance(raw_params, str | Path):
            return parameters_class.from_file(raw_params)
        return parameters_class.model_validate(raw_params)

    @abstractmethod
    def import_data(
        self, raw_data: dict[str, list[type[BusinessModel]]], parameters: module_parameters_type_var
    ) -> input_dataset_type_var:
        """Imports data using business objects and parameters."""

    @abstractmethod
    def validate_data(self, parameters: module_parameters_type_var, input_dataset: input_dataset_type_var) -> bool:
        """Validates imported or generated data."""

    @abstractmethod
    def execute(
        self, parameters: module_parameters_type_var, input_dataset: input_dataset_type_var
    ) -> output_dataset_type_var:
        """Executes the module's main logic."""

    @abstractmethod
    def validates_results(
        self,
        parameters: module_parameters_type_var,
        input_dataset: input_dataset_type_var,
        output_dataset: output_dataset_type_var,
    ) -> bool:
        """Validates results"""

    @abstractmethod
    def export_results(
        self,
        parameters: module_parameters_type_var,
        input_dataset: input_dataset_type_var,
        output_dataset: output_dataset_type_var,
    ) -> None:
        """Exports results."""

    def run(self, raw_data: dict[str, list[type[BusinessModel]]], raw_params: dict[str, Any] | str | Path) -> None:
        """Orchestrates the preparation and execution of the module.
        Should not be overridden in subclass
        """
        parameters = self.create_parameters(raw_params)

        input_dataset = self.import_data(raw_data, parameters)
        validate_data_ok = self.validate_data(parameters, input_dataset)
        if not validate_data_ok:
            raise AssertionError("Input Data/Parameters validation has not passed")

        output_dataset = self.execute(parameters, input_dataset)

        validates_results_ok = self.validates_results(parameters, input_dataset, output_dataset)
        if not validates_results_ok:
            raise AssertionError("Results validation has not passed")
        if parameters.export_result:
            self.export_results(parameters, input_dataset, output_dataset)
