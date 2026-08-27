"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import copy
import heapq
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.orchestrator.actionplan.job import (
    ActionPlanJob,
    ModuleTaskJobsGenerator,
    TaskIterationPriority,
    TaskJobsGenerator,
    WorkflowTaskJobsGenerator,
)
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters, Task, TaskModule, TaskWorkflow
from atlas.orchestrator.workflow.parameters import WorkflowParameters
from atlas.orchestrator.workflow.workflow import Workflow


class ActionPlan(AbstractOrchestrator[ActionPlanParameters, ActionPlanJob]):
    """A structure for managing the sequential execution of multiple modules and workflow through a list of action plan steps.

    Each job processes the output of the previous one, starting from the input dataset."""

    @classmethod
    def get_param_class(cls):
        return ActionPlanParameters

    def __init__(self, parameters: ActionPlanParameters):
        """Initialize a Workflow instance.

        :param parameters: Name of the workflow.
        :type parameters: WorkflowParameters
        """
        super().__init__(parameters)
        self._task_job_generators: list[TaskJobsGenerator] = []
        for task in self.parameters.tasks:
            self.add_task(task)

    def _has_concurrent_task_with(self, task: Task) -> bool:
        return any(Task.are_concurrent(itr.task, task) for itr in self._task_job_generators)

    def add_task(self, task: TaskModule | TaskWorkflow):
        """Add a task to the action plan
        :param task: task to add
        :type task: Task
        """
        root_output_dir = self.parameters.resolve_path(self.parameters.output_dir) / task.name

        _TASK_ADDER = {
            TaskModule: self._add_task_module,
            TaskWorkflow: self._add_task_workflow,
        }

        task_adder = _TASK_ADDER.get(type(task), lambda _: None)
        if task_adder is None:
            raise ValueError(f"Unknown type {type(task)} when adding {task} to Action Plan {self}")

        task_adder(task, root_output_dir)

    def _add_task_module(self, task: TaskModule, root_output_dir: Path):
        """Add a task, that run a module, and the iteration progress on it to the action plan
        :param task: task that run a module
        :type task: TaskModule
        :param root_output_dir: path to the root output directory used for the task
        :type root_output_dir: Path
        """
        if task.module is None:
            raise ValueError(f"Fail to add Task {task.name}, a TaskModule with module value None.")
        if task.parameters_path is None:
            raise ValueError(f"Fail to add Task {task.name}, a TaskModule with parameter path value None.")
        module_parameters = (
            task.module.value()
            .get_parameters_class()
            .from_file(self.parameters.resolve_path(task.parameters_path), self.parameters.context)
        )
        module_iterator = ModuleTaskJobsGenerator(task, module_parameters, root_output_dir)
        self._task_job_generators.append(module_iterator)

    def _add_task_workflow(self, task: TaskWorkflow, root_output_dir: Path):
        """Add a task, that run a workflow, to the action plan
        :param task: task that run a workflow
        :type task: TaskWorkflow
        :param root_output_dir: path to the root output directory used for the task
        :type root_output_dir: Path
        """
        if isinstance(task.workflow, Path):
            workflow_parameters = WorkflowParameters.from_file(self.parameters.resolve_path(task.workflow))
        elif isinstance(task.workflow, Workflow):
            workflow_parameters = task.workflow.parameters
        workflow_parameters.context.use(self.parameters.context)
        workflow_iterator = WorkflowTaskJobsGenerator(task, workflow_parameters, root_output_dir)
        self._task_job_generators.append(workflow_iterator)

    @property
    def jobs(self) -> Iterator[ActionPlanJob]:
        """
        Access the action plan jobs.

        :return: The list of ActionPlanJob instances.
        """
        priority_queue: list[tuple[TaskIterationPriority, int, TaskJobsGenerator]] = []
        for task_generator in self._task_job_generators:
            heapq.heappush(priority_queue, (task_generator.priority(1), 1, task_generator))

        while len(priority_queue) > 0:
            _, current_iteration, job_generator = heapq.heappop(priority_queue)
            jobs = job_generator.build_jobs(current_iteration)
            for job in jobs:
                yield cast(ActionPlanJob, job)
            next_iteration = current_iteration + 1
            if job_generator.is_valid_iteration(next_iteration):
                heapq.heappush(priority_queue, (job_generator.priority(next_iteration), next_iteration, job_generator))

    @property
    def jobs_count(self) -> int:
        return sum(len(itr) for itr in self._task_job_generators)

    def __repr__(self) -> str:
        """Return a human-readable string representation of the workflow."""
        return f"ActionPlan '{self.parameters.name}' ({len(self.parameters.tasks)} task{'s' if len(self.parameters.tasks) > 1 else ''} with a total of {self.jobs_count} step{'s' if self.jobs_count > 1 else ''})"
