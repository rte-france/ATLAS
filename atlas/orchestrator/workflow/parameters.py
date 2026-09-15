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
from atlas.io_utils.utils import deduplicate_names
from atlas.orchestrator.module_registry import ModuleRegistry


class WorkflowParameters(AbstractOrchestratorParameters):
    steps: list[Step]

    @model_validator(mode="after")
    def deduplicate_step_names(self) -> WorkflowParameters:
        for step, name in zip(
            self.steps, deduplicate_names([t.name or "unnamed_task" for t in self.steps]), strict=True
        ):
            step.name = name
        return self


class Step(BaseModel):
    """Definition of a single step

    :param name: Name identifying the step. Defaults to the module name if not provided.
    :type name: str
    :param parameters: Path to the parameters file for the job, or inline parameters for the job. Mutually exclusive with `parameters`.
    :type parameters: Path | dict
    """

    name: str | None = None
    module: ModuleRegistry
    parameters: Path | dict[str, Any]

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
