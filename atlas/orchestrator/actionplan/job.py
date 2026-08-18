"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from collections.abc import Iterator
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic_extra_types.pendulum_dt import DateTime

from atlas import WorkflowParameters
from atlas.abstract_class.job import AbstractJob
from atlas.abstract_class.module import AbstractModule
from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.io_utils.parameters import DateParameters
from atlas.io_utils.utils import deep_update
from atlas.orchestrator.actionplan.parameters import Task
from atlas.orchestrator.workflow.workflow import Workflow


class ActionPlanJob(AbstractJob):
    """
    A job in an action plan, responsible for executing a module using provided parameters plus an execution date
    and producing an output dataset from an input dataset.
    """

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow job."""
        module_name = self.module.__class__.__name__
        has_output = self._output_dataset is not None
        return f"ActionPlanStep(name={self.name!r}, module={module_name}, executed={has_output})"


class TaskIterationPriority:
    def __init__(self, execution_date: DateTime, task_priority: int):
        self.execution_date: DateTime = execution_date
        self.task_priority: int = task_priority

    def __lt__(self, other):
        if self.execution_date != other.execution_date:
            return self.execution_date < other.execution_date
        else:
            return self.task_priority < other.task_priority

    def __eq__(self, other):
        return self.execution_date == other.execution_date and self.task_priority == other.task_priority


class TaskJobsGenerator(ABC):
    """Generator associated to a Task to generate jobs based on an iteration number."""

    def __init__(self, task: Task):
        self.task: Task = task

    def start_date(self, iteration):
        """Return the start date associated to the given iteration for the task"""
        return self.execution_date(iteration) + self.task.offset_start_date

    def execution_date(self, iteration):
        """Return the execution date associated to the given iteration for the task"""
        return self.task.from_ + iteration * self.task.frequency

    def end_date(self, iteration):
        """Return the end date associated to the given iteration for the task"""
        return self.execution_date(iteration) + self.task.offset_end_date

    def priority(self, iteration) -> TaskIterationPriority:
        """Return the iteration priority associated to the given iteration for the task"""
        return TaskIterationPriority(self.execution_date(iteration), self.task.priority)

    @abstractmethod
    def build_jobs(self, iteration) -> list[AbstractJob]:
        """
        Build and return the list of ActionPlanJob for the given iteration.
        """

    def __len__(self):
        span_seconds = (self.task.until - self.task.from_).total_seconds()
        step_seconds = self.task.frequency.total_seconds()
        return int(span_seconds // step_seconds) + 1


class ModuleTaskJobsGenerator(TaskJobsGenerator):
    def __init__(self, task: Task, parameters: AbstractModuleParameters, root_output_dir: Path):
        super().__init__(task)
        if task.module is None:
            raise AttributeError(f"Task {task.name} must have a module.")

        self.module: type[AbstractModule] = task.module.value
        self.parameters: AbstractModuleParameters = parameters
        self.root_output_dir = root_output_dir

    def build_jobs(self, iteration) -> list[AbstractJob]:
        """Build and return the list of ActionPlanJob for the given iteration."""
        return [
            ActionPlanJob(
                f"task {self.task.name} iteration {iteration}",
                self.module,
                self._build_parameters(iteration),
            )
        ]

    def _build_parameters(self, iteration) -> AbstractModuleParameters:
        """Build and return parameters to use for the module for the given iteration."""
        updates: dict = {
            "temporal": DateParameters(
                start_date=self.start_date(iteration),
                end_date=self.end_date(iteration),
                execution_date=self.execution_date(iteration),
                timestep=self.parameters.temporal.timestep,
            )
        }
        if self.parameters.output is not None:
            updates["output"] = self.parameters.output.model_copy(
                update={"output_dir": self.root_output_dir / str(self.execution_date(iteration).isoformat())}
            )
        return self.parameters.model_copy(update=updates, deep=True)


class WorkflowTaskJobsGenerator(TaskJobsGenerator):
    def __init__(self, task: Task, parameters: WorkflowParameters, root_output_dir: Path):
        super().__init__(task)
        if task.workflow is None:
            raise AttributeError(f"Task {task.name} must have a workflow.")
        self.parameters: WorkflowParameters = parameters
        self.root_output_dir = root_output_dir

    def _build_parameters(self, iteration) -> WorkflowParameters:
        """Build and return parameters to use for the workflow for the given iteration."""
        parameters = self.parameters.model_copy(deep=True)
        deep_update(
            parameters.context.forced,
            {
                "temporal": {
                    "execution_date": self.execution_date(iteration),
                    "start_date": self.start_date(iteration),
                    "end_date": self.end_date(iteration),
                },
                "output": {
                    "output_dir": self.root_output_dir / str(self.execution_date(iteration).isoformat()),
                },
            },
            True,
        )
        return parameters

    def build_jobs(self, iteration) -> list[AbstractJob]:
        """Build and return the list of ActionPlanJob for the given iteration."""
        workflow = Workflow(self._build_parameters(iteration), f"task {self.task.name} iteration {iteration}")
        return list(workflow.jobs)
