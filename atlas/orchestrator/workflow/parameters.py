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
    :param parameters: Path to the parameters file for the job, or inline parameters for the job. Mutually exclusive with `parameters`.
    :type parameters: Path | str | dict
    """

    name: str | None = None
    module: ModuleRegistry
    parameters: Path | str | dict[str, Any]

    @field_validator("module", mode="before")
    @classmethod
    def coerce_module(cls, v: Any) -> ModuleRegistry:
        if isinstance(v, str):
            return ModuleRegistry(ModuleRegistry.get(v))
        return v

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters_path_exist_if_absolute(cls, v: Any) -> Path | str:
        if isinstance(v, (Path, str)) and Path(v).is_absolute() and not Path(v).exists():
            raise ValueError(f"Workflow parameters file not found at {v}")
        return v

    @model_validator(mode="after")
    def set_default_name(self) -> Step:
        if self.name is None:
            self.name = self.module.name
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
