"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractModule
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Generic

import atlas.config as cfg
from atlas.abstract_class.dataset import ID, OD
from atlas.abstract_class.parameters import P
from atlas.enums import BusinessModelName
from atlas.io_utils.atlas_dataset import AtlasDataset


class AbstractModule(ABC, Generic[P, ID, OD]):
    """Abstract base class for modules with standard execution lifecycle."""

    def before_execution(self) -> None:
        """Hook before execution."""

    def after_execution(self) -> None:
        """Hook after execution."""

    @abstractmethod
    def get_parameters_class(self) -> type[P]:
        """Returns the concrete Parameters class for this module."""

    def import_parameters(self, parameters: dict[str, Any] | str | Path | P) -> P:
        """Creates a concrete parameters object from raw dictionary or file path.

        This method provides a default implementation that handles both formats:
        - If parameters is already the right type: returns it directly
        - If parameters is dict: uses Parameters.model_validate(parameters)
        - If parameters is str/Path: uses Parameters.from_file(parameters)
        """
        parameters_class = self.get_parameters_class()

        if isinstance(parameters, parameters_class):
            return parameters
        if isinstance(parameters, str | Path):
            return parameters_class.from_file(parameters)
        return parameters_class.model_validate(parameters)

    @abstractmethod
    def import_data(self, input_data: AtlasDataset, parameters: P) -> ID:
        """Imports data using business objects and parameters."""

    @abstractmethod
    def validate_data(self, parameters: P, input_dataset: ID) -> bool:
        """Validates imported or generated data."""

    @abstractmethod
    def execute(self, parameters: P, input_dataset: ID) -> OD:
        """Executes the module's main logic."""

    @abstractmethod
    def validates_results(
        self,
        parameters: P,
        input_dataset: ID,
        output_dataset: OD,
    ) -> bool:
        """Validates results"""

    @abstractmethod
    def export_results(
        self,
        parameters: P,
        input_dataset: ID,
        output_dataset: OD,
    ) -> None:
        """Exports results."""

    def run(self, input_data: AtlasDataset, parameters: dict[str, Any] | str | Path | P) -> OD:
        """Orchestrates the preparation and execution of the module.
        Should not be overridden in subclass
        """
        params = self.import_parameters(parameters)

        input_dataset = self.import_data(input_data, params)
        validate_data_ok = self.validate_data(params, input_dataset)
        if not validate_data_ok:
            raise AssertionError("Input Data/Parameters validation has not passed")

        output_dataset = self.execute(params, input_dataset)
        output_dataset.build_change_sets()

        validates_results_ok = self.validates_results(params, input_dataset, output_dataset)
        if not validates_results_ok:
            raise AssertionError("Results validation has not passed")
        self.export_results(params, input_dataset, output_dataset)
        return output_dataset

    @staticmethod
    def get_business_model_class_used() -> Iterable[BusinessModelName]:
        return cfg.MODEL_MAPPING_NAME.keys()

    @staticmethod
    def get_filters():
        return None
