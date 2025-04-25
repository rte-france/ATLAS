"""
Copyright (c) 2025, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractModule
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from atlas import BusinessModel
from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.abstract_class.abstract_dataset import AbstractDataset


class AbstractModule(ABC):
    """Abstract base class for modules with standard execution lifecycle."""

    @abstractmethod
    def export_kpi(self) -> None:
        """Exports KPIs."""

    @abstractmethod
    def before_execution(self) -> None:
        """Hook before execution."""

    @abstractmethod
    def after_execution(self) -> None:
        """Hook after execution."""

    @abstractmethod
    def read_parameters(self, path: Path) -> dict[str, Any]:
        """Reads parameters from a file using a concrete Pydantic class."""

    @abstractmethod
    def get_parameter(self, name: str) -> Any:
        """Returns the value of the specified parameter."""

    @abstractmethod
    def create_parameters(self, raw_params: dict[str, Any]) -> AbstractParameters:
        """Creates a concrete parameters object from raw dictionary."""

    @abstractmethod
    def import_data(self, objects: list[BusinessModel], parameters: AbstractParameters) -> AbstractDataset:
        """Imports data using business objects and parameters."""

    @abstractmethod
    def execute(self, parameters: AbstractParameters, input_dataset: AbstractDataset) -> AbstractDataset:
        """Executes the module's main logic."""

    @abstractmethod
    def validate_data(self, parameters: AbstractParameters, input_dataset: AbstractDataset) -> bool:
        """Validates imported or generated data."""

    @abstractmethod
    def sanity_check(self, parameters: AbstractParameters, input_dataset: AbstractDataset, output_dataset:
                     AbstractDataset) -> bool:
        """Validates results"""

    def run(self, objects: list[BusinessModel], parameters_path: Path) -> None:
        """Orchestrates the preparation and execution of the module."""
        raw_params = self.read_parameters(parameters_path)
        parameters = self.create_parameters(raw_params)

        input_dataset = self.import_data(objects, parameters)
        sanitize_data_ok = self.validate_data(parameters, input_dataset)
        if sanitize_data_ok:
            output_dataset = self.execute(parameters, input_dataset)
        else:
            pass  # raise Error
        sanity_check_ok = self.sanity_check(parameters, input_dataset, output_dataset)
        if sanity_check_ok:
            self.export_kpi()
        else:
            pass  # raise Error
