"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import heapq
import copy
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.orchestrator.actionplan.job import (
    ActionPlanJob,
    ModuleTaskJobsGenerator,
    TaskJobsGenerator,
    WorkflowTaskJobsGenerator,
    TaskIterationPriority,
)
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters, Task
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
        self._priority_queue: list[tuple[TaskIterationPriority, int, TaskJobsGenerator]] = []
        self._build_priority_queue()

    def _has_concurrent_task_with(self, task: Task) -> bool:
        return any(Task.are_concurrent(itr.task, task) for _, _, itr in self._priority_queue)

    def add_task(self, task: Task) -> int:
        """Add a task to the action plan and return the number of jobs added
        :param task: task to add
        :type task: Task
        """
        root_output_dir = self.parameters.resolve_path(self.parameters.output_dir) / task.name
        if task.module is not None:
            return self._add_task_module(task, root_output_dir, 0)
        elif task.workflow is not None:
            return self._add_task_workflow(task, root_output_dir, 0)
        return 0

    def _add_task_module(self, task: Task, root_output_dir: Path, next_iteration: int) -> int:
        """Add a task, that run a module, and the iteration progress on it to the action plan and return the number of job add
        :param task: task that run a module
        :type task: Task
        :param root_output_dir: path to the root output directory used for the task
        :type root_output_dir: Path
        :param next_iteration: next iteration for which the task will be used
        :type next_iteration: int
        """
        if task.module is None:
            raise ValueError("_add_task_module called without a module")
        if task.module_parameters_path is None:
            raise ValueError("_add_task_module called without a module parameter path")
        module_parameters = (
            task.module.value()
            .get_parameters_class()
            .from_file(self.parameters.resolve_path(task.module_parameters_path), self.parameters.context)
        )
        module_iterator = ModuleTaskJobsGenerator(task, module_parameters, root_output_dir)
        return self._push_iterator(module_iterator, next_iteration)

    def _add_task_workflow(self, task: Task, root_output_dir: Path, next_iteration: int) -> int:
        """Add a task, that run a workflow, to the action plan and return the number of job add
        :param task: task that run a workflow
        :type task: Task
        :param root_output_dir: path to the root output directory used for the task
        :type root_output_dir: Path
        :param next_iteration: next iteration for which the task will be used
        :type next_iteration: int
        """
        if isinstance(task.workflow, Path):
            workflow_parameters = WorkflowParameters.from_file(self.parameters.resolve_path(task.workflow))
        elif isinstance(task.workflow, Workflow):
            workflow_parameters = task.workflow.parameters
        workflow_parameters.context.use(self.parameters.context)
        workflow_iterator = WorkflowTaskJobsGenerator(task, workflow_parameters, root_output_dir)
        return self._push_iterator(workflow_iterator, next_iteration)

    def _push_iterator(self, iterator: TaskJobsGenerator, next_iteration: int) -> int:
        """Add an iterator to the priority queue and return the number of jobs added
        :param iterator: iterator to add
        :type iterator: TaskGenerator
        :param next_iteration: next iteration for which the task will be used
        :type next_iteration: int
        """
        if self._has_concurrent_task_with(iterator.task):
            raise ValueError("Try to add a concurrent task to the Action plan")
        heapq.heappush(self._priority_queue, (iterator.priority(next_iteration), next_iteration, iterator))
        return len(iterator)

    def _pop_iterator(self):
        """Remove and return the next iterator in the priority queue"""
        _, iteration, task_generator = heapq.heappop(self._priority_queue)
        return iteration, task_generator

    def _build_priority_queue(self):
        self._priority_queue.clear()
        for task in self.parameters.tasks:
            self.add_task(task)

    @property
    def jobs(self) -> Iterator[ActionPlanJob]:
        """
        Access the action plan jobs.

        :return: The list of ActionPlanJob instances.
        """
        cc = copy.deepcopy(self._priority_queue)
        while len(self._priority_queue) > 0:
            next_iteration, job_generator = self._pop_iterator()
            jobs = job_generator.build_jobs(next_iteration)
            if jobs is not None:
                self._push_iterator(job_generator, next_iteration + 1)
                for job in jobs:
                    yield cast(ActionPlanJob, job)
        self._priority_queue = cc

    @property
    def jobs_count(self) -> int:
        return sum(len(itr) for _, _, itr in self._priority_queue)

    def __repr__(self) -> str:
        """Return a human-readable string representation of the workflow."""
        return f"ActionPlan '{self.parameters.name}' ({len(self.parameters.tasks)} task{'s' if len(self.parameters.tasks) > 1 else ''} with a total of {self.jobs_count} step{'s' if self.jobs_count > 1 else ''})"
