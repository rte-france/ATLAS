"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from atlas import WorkflowParameters
from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.orchestrator.actionplan.job import ActionPlanJob, ModuleTaskIterator, TaskIterator, WorkflowTaskIterator
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters, Task
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
        self._priority_queue: list[TaskIterator] = []
        self._build_priority_queue()

    def _has_concurrent_task_with(self, task: Task) -> bool:
        return any(Task.are_concurrent(itr.task, task) for itr in self._priority_queue)

    def add_task(self, task: Task) -> int:
        """Add a task to the action plan and return the number of jobs added
        :param task: task to add
        :type task: Task
        """
        root_output_dir = self.parameters.resolve_path(self.parameters.output_dir) / task.name
        if task.module is not None:
            return self._add_task_module(task, root_output_dir)
        elif task.workflow is not None:
            return self._add_task_workflow(task, root_output_dir)
        return 0

    def _add_task_module(self, task: Task, root_output_dir: Path) -> int:
        """Add a task, that run a module, to the action plan and return the number of job add
        :param task: task that run a module
        :type task: Task
        :param root_output_dir: path to the root output directory used for the task
        :type root_output_dir: Path
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
        module_iterator = ModuleTaskIterator(task, module_parameters, root_output_dir)
        return self._push_iterator(module_iterator)

    def _add_task_workflow(self, task: Task, root_output_dir: Path) -> int:
        """Add a task, that run a workflow, to the action plan and return the number of job add
        :param task: task that run a workflow
        :type task: Task
        :param root_output_dir: path to the root output directory used for the task
        :type root_output_dir: Path
        """
        if isinstance(task.workflow, Path):
            workflow_parameters = WorkflowParameters.from_file(self.parameters.resolve_path(task.workflow))
        elif isinstance(task.workflow, Workflow):
            workflow_parameters = task.workflow.parameters
        workflow_parameters.context.use(self.parameters.context)
        workflow_iterator = WorkflowTaskIterator(task, workflow_parameters, root_output_dir)
        return self._push_iterator(workflow_iterator)

    def _push_iterator(self, iterator: TaskIterator) -> int:
        """Add an iterator to the priority queue and return the number of jobs added
        :param iterator: iterator to add
        :type iterator: TaskIterator
        """
        if self._has_concurrent_task_with(iterator.task):
            raise ValueError("Try to add a concurrent task to the Action plan")
        heapq.heappush(self._priority_queue, iterator)
        return len(iterator)

    def _pop_iterator(self) -> TaskIterator:
        """Remove and return the next iterator in the priority queue"""
        itr = heapq.heappop(self._priority_queue)
        return itr

    def _build_priority_queue(self) -> None:
        """Build the priority queue and update the number of jobs in the action plan."""
        self._jobs_count = 0
        for task in self.parameters.tasks:
            self._jobs_count += self.add_task(task)

    @property
    def jobs(self) -> Iterator[ActionPlanJob]:
        """
        Access the action plan jobs.

        :return: The list of ActionPlanJob instances.
        """
        if len(self._priority_queue) == 0:
            self._build_priority_queue()
        while len(self._priority_queue) > 0:
            priority_task_itr = self._pop_iterator()
            jobs = next(priority_task_itr, None)
            if jobs is not None:
                self._push_iterator(priority_task_itr)
                for job in jobs:
                    yield cast(ActionPlanJob, job)

    @property
    def jobs_count(self) -> int:
        return self._jobs_count

    def __repr__(self) -> str:
        """Return a human-readable string representation of the workflow."""
        return f"ActionPlan '{self.parameters.name}' ({len(self.parameters.tasks)} task{'s' if len(self.parameters.tasks) > 1 else ''} with a total of {self.jobs_count} step{'s' if self.jobs_count > 1 else ''})"
