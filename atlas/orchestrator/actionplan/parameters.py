"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from pendulum import Duration
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.abstract_class.orchestrator_parameters import AbstractOrchestratorParameters
from atlas.orchestrator.hook.hook import Hook
from atlas.orchestrator.module_registry import ModuleRegistry
from atlas.orchestrator.workflow.workflow import Workflow
from atlas.validators import convert_to_duration


# FIXME Move this class to an other file
class DataQualityWarning(UserWarning):
    """Warning for potential input data quality issues."""

    pass


class ActionPlanParameters(AbstractOrchestratorParameters):
    """Parameters for the action plan.
    :param tasks: List of tasks to execute
    :type tasks: list[Task]
    :param hooks: List of hooks in the workflow
    :type hooks: list[Hook]
    """

    tasks: list[Task]
    hooks: list[Hook] = []

    @model_validator(mode="after")
    def task_with_workflow_can_be_built(self) -> ActionPlanParameters:
        for task in self.tasks:
            if task.workflow is not None and isinstance(task.workflow, Path):
                try:
                    workflow = Workflow.from_file(task.workflow, self.context)
                except ValueError as e:
                    raise ValueError(f"An exception occurred when building Workflow for task {task.name} using parameters {task.workflow} : {e}")
                task.workflow = workflow
        return self

class Task(BaseModel):
    """Definition of a single task

    :param name: Name of the action plan task.
    :type name: str
    :param module: Module to be executed (if any) in this task.
    :type module: AbstractModule | None
    :param parameters_path: Parameters of the module or the workflow associated with this task.
    :type parameters_path: str
    :param workflow: Workflow to be executed (if any) in this task.
    :type workflow: string | None
    :param priority: Priority of the action plan task.
    :type priority: int
    :param from_: First date time to execute this task.
    :type from_: DateTime
    :param until: Last date time to execute this task.
    :type until: DateTime
    :param frequency: Frequency of the action plan task.
    :type frequency: Duration
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str | None = None
    module: ModuleRegistry | None = None
    workflow: Path | None = None #FIXME NB: we can't build the Workflow at this step since we lack the context that may contains missing parameters in workflow parameters, any idea?
    parameters_path: Path
    priority: int
    from_: DateTime  # FIXME change name, "from" isn't available in python
    until: DateTime
    frequency: Duration
    offset_start_date: Duration
    offset_end_date: Duration

    @field_validator("module", mode="before")
    @classmethod
    def coerce_module(cls, v: Any) -> ModuleRegistry | None:
        if v is not None and isinstance(v, str):
            return ModuleRegistry(ModuleRegistry.get(v))
        return v

    @field_validator("workflow", mode="before")
    @classmethod
    def check_workflow_exist(cls, v: Any) -> Path | None:
        if v is not None and isinstance(v, Path):
            v.exists()
            return v
        return v

    @field_validator(
        "frequency",
        "offset_start_date",
        "offset_end_date",
        mode="before",
    )
    @classmethod
    def parse_duration(cls, v):
        """Convert various duration formats to Duration objects."""
        return convert_to_duration(v)

    @model_validator(mode="after")
    def module_or_workflow(self) -> Task:  # FIXME better function name? Can we overide validate()
        if self.module is None and self.workflow is None:
            raise ValueError(
                f"Task {self.name} doesn't contains either a module or a workflow, expected exactly one of them"
            )  # FIXME More appropriate exception name?
        if self.module is not None and self.workflow is not None:
            raise ValueError(
                f"Task {self.name} contains both a module or a workflow, expected exactly one of them"
            )  # FIXME More appropriate exception name?
        return self

    @model_validator(mode="after")
    def until_from_frequency(self) -> Task:  # FIXME Can we override validate()?
        if self.until < self.from_:
            raise ValueError(
                f"Task {self.name} must have an 'until' date before 'from' date {self.from_}, current value is {self.until}"
            )
        timedelta = self.until - self.from_
        if timedelta.total_seconds() % (self.frequency.total_seconds()) != 0:
            diff_seconds = timedelta.total_seconds() % (self.frequency.total_seconds())
            last_execution_date = self.until - Duration(seconds=diff_seconds)
            warnings.warn(
                f"Task {self.name} last execution date is not equal to 'until' {self.until}', last value is {last_execution_date}",
                DataQualityWarning,
                stacklevel=2,
            )
        return self