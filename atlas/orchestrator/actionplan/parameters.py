"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import warnings
from abc import ABC
from math import gcd
from pathlib import Path
from typing import Any

from pendulum import Duration, duration
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.abstract_class.orchestrator_parameters import AbstractOrchestratorParameters
from atlas.abstract_class.parameters import AbstractModuleParameters
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

    tasks: list[TaskModule | TaskWorkflow]
    hooks: list[Hook] = []

    @model_validator(mode="after")
    def concurrent_tasks(self) -> ActionPlanParameters:
        for idx, t1 in enumerate(self.tasks):
            for t2 in self.tasks[idx + 1 :]:
                if Task.are_concurrent(t1, t2):
                    raise ValueError(f"Action plan {self.name} contains two concurrent tasks:\n{t1}\n{t2}")
        return self


class Task(BaseModel, ABC):
    """Base definition of any task

    :param name: Name of the action plan task.
    :type name: str
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
        """Return true if both task are concurrent, meaning they both have the same priority and, at some point, have to be executed with the same execution."""
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


class TaskModule(Task):
    """Definition of a single task that run a module

    :param module: Module to be executed (if any) in this task.
    :type module: AbstractModule | None
    :param parameters: Parameters of the module associated with this task.
    :type parameters: AbstractModuleParameters | dict[str, Any] | str | Path
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    module: ModuleRegistry
    parameters: AbstractModuleParameters | dict[str, Any] | str | Path

    @field_validator("module", mode="before")
    @classmethod
    def coerce_module(cls, v: Any) -> ModuleRegistry | None:
        if v is not None and isinstance(v, str):
            return ModuleRegistry(ModuleRegistry.get(v))
        return v

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_module_path_exist_if_absolute(cls, v: Any) -> Path | None:
        if v is not None:
            if isinstance(v, Path) and v.is_absolute() and not v.exists():
                raise ValueError(f"Module parameters file not found at {v}")
            if isinstance(v, str) and Path(v).is_absolute() and not Path(v).exists():
                raise ValueError(f"Module parameters file not found at {v}")
        return v

    @model_validator(mode="after")
    def default_name(self) -> TaskModule:
        if self.name is None and self.module is not None:
            self.name = self.module.name
        return self


class TaskWorkflow(Task):
    """Definition of a single task that run a workflow

    :param workflow: Workflow to be executed, can be a path to a config file to build it.
    :type workflow: Workflow | Path
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    workflow: Workflow | dict[str, Any] | str | Path

    @field_validator("workflow", mode="before")
    @classmethod
    def build_workflow(cls, v: Any) -> Workflow:
        if isinstance(v, Path):
            return Workflow.from_file(v)
        return v

    @field_validator("workflow", mode="before")
    @classmethod
    def validate_workflow_path_exist_if_absolute(cls, v: Any) -> Path | None:
        if v is not None:
            if isinstance(v, Path) and v.is_absolute() and not v.exists():
                raise ValueError(f"Workflow parameters file not found at {v}")
            if isinstance(v, str) and Path(v).is_absolute() and not Path(v).exists():
                raise ValueError(f"Workflow parameters file not found at {v}")
        return v

    @model_validator(mode="after")
    def default_name(self) -> TaskWorkflow:
        if self.name is None:
            if isinstance(self.workflow, Workflow):
                self.name = self.workflow.parameters.name
            elif isinstance(self.workflow, dict) and "name" in self.workflow:
                self.name = self.workflow["name"]
            elif isinstance(self.workflow, (Path, str)):
                self.name = Path(self.workflow).stem
        return self
