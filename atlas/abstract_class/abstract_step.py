"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, field_validator, model_validator

from atlas import AtlasDataset
from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.orchestrator.module_registry import ModuleRegistry


class AbsractStep:
    """
    A step in an orchestrator, responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __init__(self, name: str, module: type[AbstractModule], parameters: dict[str, Any]):
        """
        Initialize an AbstractStep.

        :param name: Name of the step.
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
        Get the output dataset produced by this orchestrator step.

        :return: An AbstractDataset or None if not yet executed.
        """
        return self._output_dataset

    def run(self, input_dataset: AtlasDataset) -> None:
        """
        Execute the step's module with the given parameters and input dataset.
        Stores the resulting dataset as output.
        """
        self._output_dataset = self.module.run(input_dataset, self.parameters)


S = TypeVar("S", bound=AbsractStep)
