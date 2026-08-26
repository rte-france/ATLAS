"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from atlas.abstract_class.orchestrator_parameters import AbstractOrchestratorParameters
from atlas.orchestrator.module_registry import ModuleRegistry


class WorkflowParameters(AbstractOrchestratorParameters):
    steps: list[Step]


class Step(BaseModel):
    """Definition of a single step

    :param name: Name identifying the step. Defaults to the module name if not provided.
    :type name: str
    :param parameters_path: Path to the parameters file for the job. Mutually exclusive with `parameters`.
    :type parameters_path: str | None
    :param parameters: Inline parameters for the job. Mutually exclusive with `parameters_path`.
    :type parameters: dict | None
    """

    name: str | None = None
    module: ModuleRegistry
    parameters_path: Path | None = None
    parameters: dict | None = None

    @field_validator("module", mode="before")
    @classmethod
    def coerce_module(cls, v: Any) -> ModuleRegistry:
        if isinstance(v, str):
            return ModuleRegistry(ModuleRegistry.get(v))
        return v

    @model_validator(mode="after")
    def set_default_name(self) -> Step:
        if self.name is None:
            self.name = self.module.name
        return self

    @model_validator(mode="after")
    def check_parameters_source(self) -> Step:
        if (self.parameters_path is None) == (self.parameters is None):
            raise ValueError("Exactly one of 'parameters_path' or 'parameters' must be set.")
        return self

    @staticmethod
    def add_index_in_step_name(steps: list[Step]) -> None:
        """Append a numeric index suffix to duplicate step names, in-place.

        Steps whose name is unique are left unchanged. Steps sharing a name are
        renamed '<name>_1', '<name>_2', etc., in the order they appear.

        :param steps: List of step parameter objects exposing a 'name' attribute.
        :type steps: list
        """
        name_counts: dict[str, int] = {}
        for step in steps:
            name_counts[step.name] = name_counts.get(step.name, 0) + 1  # type: ignore[index, arg-type]

        name_index: dict[str, int] = {}
        for step in steps:
            if name_counts[step.name] > 1:  # type: ignore[index]
                name_index[step.name] = name_index.get(step.name, 0) + 1  # type: ignore[index, arg-type]
                step.name = f"{step.name}_{name_index[step.name]}"  # type: ignore[index]
