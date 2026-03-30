"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from atlas import AtlasDataset
from atlas.abstract_class.abstract_dataset import AbstractModuleOutput

class ActionPlanStep:
    """
    A step in a workflow, responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __init__(self, name: str, parameters: dict[str, Any]):
        raise NotImplementedError

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
        raise NotImplementedError

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow step."""
        raise NotImplementedError
