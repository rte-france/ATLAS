"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic_extra_types.pendulum_dt import DateTime

from atlas import WorkflowParameters
from atlas.abstract_class.job import AbstractJob
from atlas.abstract_class.module import AbstractModule
from atlas.abstract_class.parameters import AbstractModuleParameters
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


class TaskIterator(ABC):
    def __init__(self, task: Task):
        self.task: Task = task
        self.next_execution_date: DateTime = task.from_

    @property
    def next_start_date(self):
        return self.task.offset_start_date + self.next_execution_date

    @property
    def next_end_date(self):
        return self.task.offset_end_date + self.next_execution_date

    def __iter__(self):
        self.next_execution_date = self.task.from_
        return self

    def __next__(self) -> list[AbstractJob]:
        if self.next_execution_date > self.task.until:
            raise StopIteration()  # Signals the end of iteration
        jobs = self.build_jobs()
        self.next_execution_date += self.task.frequency
        return jobs

    @abstractmethod
    def build_jobs(self) -> list[AbstractJob]:
        """
        Build and return the list of ActionPlanJob with execution date value as the next date.
        """

    def __len__(self):
        # TODO better computation
        acc = 0
        d = self.next_execution_date
        while d <= self.task.until:
            acc += 1
            d += self.task.frequency
        return acc

    def __lt__(self, other):
        if self.next_execution_date != other.next_execution_date:
            return self.next_execution_date < other.next_execution_date
        else:
            return self.task.priority < other.task.priority

    def __eq__(self, other):
        return self.next_execution_date == other.next_execution_date and self.task.priority == other.task.priority


class ModuleTaskIterator(TaskIterator):
    def __init__(self, task: Task, parameters: AbstractModuleParameters, root_output_dir: Path):
        super().__init__(task)
        if task.module is None:
            raise AttributeError("Task must have a module.")

        self.module: type[AbstractModule] = task.module.value
        self.parameters: AbstractModuleParameters = parameters
        self.root_output_dir = root_output_dir

    def build_jobs(self) -> list[AbstractJob]:
        return [ActionPlanJob("insert_name", self.module, self.build_current_parameters())]

    def build_current_parameters(self) -> AbstractModuleParameters:
        parameters = copy.deepcopy(self.parameters)
        parameters.output.output_dir = self.root_output_dir / self.next_execution_date
        parameters.temporal.start_date = self.next_start_date
        parameters.temporal.end_date = self.next_end_date
        parameters.temporal.execution_date = self.next_execution_date
        return parameters


class WorkflowTaskIterator(TaskIterator):
    def __init__(self, task: Task, parameters: WorkflowParameters, root_output_dir: Path):
        super().__init__(task)
        self.parameters: WorkflowParameters = parameters
        self.root_output_dir = root_output_dir

    def build_current_parameters(self) -> WorkflowParameters:
        parameters = copy.deepcopy(self.parameters)
        deep_update(
            parameters.context.forced,
            {
                "temporal": {
                    "execution_date": self.task.until,
                    "start_date": self.next_start_date,
                    "end_date": self.next_end_date,
                },
                "output": {
                    "output_dir": self.root_output_dir / self.next_execution_date,
                },
            },
            True,
        )
        return parameters

    def build_jobs(self) -> list[AbstractJob]:
        workflow = Workflow(self.build_current_parameters())
        return list(workflow.jobs)
