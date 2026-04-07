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
    """Definition of a single step

    :param name: Name identifying the step. Defaults to the module name if not provided.
    :type name: str
    :param parameters_path: Path to the parameters file for the step.
    :type parameters_path: str
    """

    name: str | None = None
    module: AbstractModule
    parameters_path: Path

    def __init__(self, name: str, module: type[AbstractModule], parameters: dict[str, Any]):
        """
        Initialize an orchestrator Step.

        :param name: Name of the step.
        :type name: str
        :param module: Module to be executed in this step.
        :type module: AbstractModule
        :param parameters: Parameter for the module.
        :type parameters: AbstractParameters
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

    @field_validator("module", mode="before")
    @classmethod
    def coerce_module(cls, v: Any) -> ModuleRegistry:
        if isinstance(v, str):
            return ModuleRegistry(ModuleRegistry.get(v))
        return v

    @model_validator(mode="after")
    def set_default_name(self) -> AbsractStep:
        if self.name is None:
            self.name = self.module.__class__.__name__
        return self


S = TypeVar("S", bound=AbsractStep)
