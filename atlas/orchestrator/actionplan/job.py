"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pendulum import DateTime, Duration
from pydantic import BaseModel, field_validator, model_validator

from atlas import Workflow
from atlas.abstract_class.job import AbstractJob
from atlas.orchestrator.module_registry import ModuleRegistry


class ActionPlanJob(AbstractJob):
    """
    A job in an action plan is responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow job."""
        module_name = self.module.__class__.__name__
        has_output = self._output_dataset is not None
        return f"ActionPlanStep(name={self.name!r}, module={module_name}, executed={has_output})"


class Task(BaseModel):
    """Definition of a single job

    :param name: Name of the action plan job.
    :type name: str
    :param module: Module to be executed (if any) in this job.
    :type module: AbstractModule | None
    :param parameters_path: Parameters of the module or the workflow associated with this task.
    :type parameters_path: str | None
    :param workflow: Workflow to be executed (if any) in this job.
    :type workflow: string | None
    :param priority: Priority of the action plan job.
    :type priority: int
    :param from_: First date time to execute this job.
    :type from_: DateTime
    :param until: Last date time to execute this job.
    :type until: DateTime
    :param frequency: Frequency of the action plan job.
    :type frequency: Duration
    """

    name: str | None = None
    module: ModuleRegistry | None = None
    workflow: Workflow | None = None
    parameters_path: Path | None = None
    priority: int
    from_: DateTime  # FIXME change name, "from" isn't available in python
    until: DateTime
    frequency: Duration

    def associated_jobs_with_execution_date(self, execution_date: DateTime) -> list[ActionPlanJob]:
        """
        Return the list of job executed by an iteration of this task with the given execution date.
        """
        raise NotImplementedError

    @field_validator("workflow", mode="before")
    @classmethod
    def coerce_workflow(cls, v: Any) -> Workflow | None:
        if v is not None and isinstance(v, str):
            return Workflow.from_file(v)
        return v

    @field_validator("module", mode="before")
    @classmethod
    def coerce_module(cls, v: Any) -> ModuleRegistry | None:
        if v is not None and isinstance(v, str):
            return ModuleRegistry(ModuleRegistry.get(v))
        return v

    @model_validator(mode="after")
    def module_or_workflow(self) -> Task:  # FIXME better function name? Can we overide validate()
        if self.module is None and self.workflow is None:
            raise ValueError(
                f"Task {self.name} doesn't contains either a module or a workflow, expected exactly once of them"
            )  # FIXME More appropriate exception name?
        if self.module is not None and self.workflow is not None:
            raise ValueError(
                f"Task {self.name} contains both a module or a workflow, expected exactly once of them"
            )  # FIXME More appropriate exception name?
        if self.until <= self.from_:
            raise ValueError(
                f"Task {self.name} must have an end date before {self.from_}, current value is {self.until}"
            )
        return self
