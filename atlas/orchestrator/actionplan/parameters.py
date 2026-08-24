"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import warnings
from math import gcd
from pathlib import Path
from typing import Any

from pendulum import Duration, duration
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.abstract_class.orchestrator_parameters import AbstractOrchestratorParameters
from atlas.custom_errors import DataQualityWarning
from atlas.orchestrator.hook.hook import Hook
from atlas.orchestrator.module_registry import ModuleRegistry
from atlas.orchestrator.workflow.workflow import Workflow
from atlas.validators import DurationField


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
    def concurrent_tasks(self) -> ActionPlanParameters:
        for idx, t1 in enumerate(self.tasks):
            for t2 in self.tasks[idx + 1 :]:
                if Task.are_concurrent(t1, t2):
                    raise ValueError(f"Action plan {self.name} contains two concurrent tasks:\n{t1}\n{t2}")
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
    workflow: Workflow | Path | None = None
    module_parameters_path: Path | None = None
    priority: int = 0
    from_: DateTime = Field(validation_alias=AliasChoices("from", "from_"))
    until: DateTime
    frequency: DurationField = Field(
        default_factory=lambda: duration(minutes=1),
        description="Discretization step of the execution date",
    )
    offset_start_date: DurationField = Field(
        default_factory=lambda: duration(minutes=0),
        description="Offset duration from the execution date the start date have",
    )
    offset_end_date: DurationField = Field(
        default_factory=lambda: duration(minutes=0),
        description="Offset duration from the execution date the end date have",
    )

    @classmethod
    def are_concurrent(cls, task1: Task, task2: Task) -> bool:
        # Different priority are ignored
        if task1.priority != task2.priority:
            return False

        # Concurrent impossible
        if task1.from_ > task2.until or task1.until < task2.from_:
            return False

        # With same frequency, will be concurrent if diff in from is a multiple of frequency
        if task1.frequency == task2.frequency:
            return (task1.from_ - task2.from_).total_seconds() % task1.frequency.total_seconds() == 0

        # Otherwise, they will be concurrent on exactly one date, using Bézout's identity we can close some cases
        g = gcd(int(task1.frequency.total_seconds()), int(task2.frequency.total_seconds()))
        delta_from = int((task1.from_ - task2.from_).total_seconds())
        if delta_from % g != 0:
            return False

        # We know brute force to check if there exist a concurrent date
        date1 = task1.from_
        date2 = task2.from_
        while date1 != date2 and date1 <= task1.until and date2 <= task2.until:
            if date1 < date2:
                date1 = date1 + task1.frequency
            else:
                date2 = date2 + task2.frequency
        return date1 == date2

    @field_validator("module", mode="before")
    @classmethod
    def coerce_module(cls, v: Any) -> ModuleRegistry | None:
        if v is not None and isinstance(v, str):
            return ModuleRegistry(ModuleRegistry.get(v))
        return v

    @field_validator("module_parameters_path", mode="before")
    @classmethod
    def validate_module_path_exist(cls, v: Any) -> Path | None:
        if v is not None and isinstance(v, Path):
            if not v.exists():
                raise ValueError(f"Module parameters file not found at {v}")
        return v

    @field_validator("workflow", mode="before")
    @classmethod
    def validate_workflow_exist(cls, v: Any) -> Workflow | None:
        if v is not None and isinstance(v, Path):
            if not v.exists():
                raise ValueError(f"Workflow parameter file not found at {v}")
        return v

    @model_validator(mode="after")
    def default_name(self) -> Task:
        if self.name is None:
            if self.module is not None:
                self.name = self.module.name
            if self.workflow is not None:
                if isinstance(self.workflow, Path):
                    self.name = self.workflow.name
                elif isinstance(self.workflow, Workflow):
                    self.name = self.workflow.parameters.name
        return self

    @model_validator(mode="after")
    def module_or_workflow(self) -> Task:
        if self.module is not None and self.module_parameters_path is None:
            raise ValueError(f"Task {self.name} have a module {self.module} but no parameter file")
        if self.module is None and self.module_parameters_path is not None:
            raise ValueError(
                f"Task {self.name} do not have a module but has a module parameter file {self.module_parameters_path}"
            )
        if self.module is None and self.workflow is None:
            raise ValueError(
                f"Task {self.name} doesn't contains either a module or a workflow, expected exactly one of them"
            )
        if self.module is not None and self.workflow is not None:
            raise ValueError(f"Task {self.name} contains both a module or a workflow, expected exactly one of them")
        return self

    @model_validator(mode="after")
    def until_from_frequency(self) -> Task:
        if self.until < self.from_:
            raise ValueError(
                f"Task {self.name} must have an 'until' date before 'from' date {self.from_}, current value is {self.until}"
            )
        timedelta = self.until - self.from_
        diff_seconds = timedelta.total_seconds() % (self.frequency.total_seconds())
        if diff_seconds != 0:
            last_execution_date = self.until - Duration(seconds=diff_seconds)
            warnings.warn(
                f"Task {self.name} last execution date is not equal to 'until' {self.until}', last value is {last_execution_date}",
                DataQualityWarning,
                stacklevel=2,
            )
        return self
