"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import Any

from atlas import AtlasDataset
from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.abstract_class.abstract_module import AbstractModule


class WorkflowStep:
    """
    A step in a workflow, responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __init__(self, name: str, module: type[AbstractModule], parameters: dict[str, Any]):
        """
        Initialize a WorkflowStep.

        :param name: Name of the workflow step.
        :type name: str
        :param module: Module to be executed in this step.
        :type module: AbstractModule
        :param parameters: Parameter for the module.
        :type parameters: AbstractModuleParameters
        """
        self.name: str = name
        self.module = module()
        self.parameters = self.module.get_parameters_class().model_validate(parameters)
        self._output_dataset: AbstractModuleOutput | None = None

    @property
    def output_dataset(self) -> AbstractModuleOutput | None:
        """
        Output dataset produced after executing the step.

        :return: An AbstractDataset or None if not yet executed.
        """
        return self._output_dataset

    def get_output_dataset(self) -> AbstractModuleOutput | None:
        """
        Get the output dataset produced by this workflow step.

        :return: An AbstractDataset or None if not yet executed.
        """
        return self._output_dataset

    def run(self, input_dataset: AtlasDataset) -> None:
        """
        Execute the step's module with the given parameters and input dataset.
        Stores the resulting dataset as output.
        """
        self._output_dataset = self.module.run(input_dataset, self.parameters)

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow step."""
        module_name = self.module.__class__.__name__
        has_output = self._output_dataset is not None
        return f"WorkflowStep(name={self.name!r}, module={module_name}, executed={has_output})"
