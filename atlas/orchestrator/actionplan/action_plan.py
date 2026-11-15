"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import heapq
from collections import namedtuple
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.custom_errors import UseContextError
from atlas.io_utils.parameters import ContextParameters
from atlas.io_utils.utils import deep_update
from atlas.orchestrator.actionplan.job import (
    ActionPlanJob,
    ModuleTaskJobsGenerator,
    TaskJobsGenerator,
    WorkflowTaskJobsGenerator,
)
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters, Task, TaskModule, TaskWorkflow
from atlas.orchestrator.workflow.parameters import WorkflowParameters


class ActionPlan(AbstractOrchestrator[ActionPlanParameters, ActionPlanJob]):
    """A structure for managing the sequential execution of multiple modules and workflow through a list of action plan steps.

    Each job processes the output of the previous one, starting from the input dataset."""

    @classmethod
    def get_param_class(cls) -> type[ActionPlanParameters]:
        return ActionPlanParameters

    def __init__(self, parameters: ActionPlanParameters):
        """Initialize an ActionPlan instance.

        :param parameters: Parameters of the action plan, including its tasks and hooks.
        :type parameters: ActionPlanParameters
        """
        super().__init__(parameters)
        self._raw_tasks: list[TaskModule | TaskWorkflow] = []
        self._task_job_generators: list[TaskJobsGenerator] = []
        for task in self.parameters.tasks:
            self.add_task(task)

    def has_task_concurrent_with(self, task: Task) -> bool:
        """Return true if given task and a task from this action plan have the same priority and, at some point, have to be executed with the same execution."""
        return any(
            existing_task_generator.concurrent_with(task) for existing_task_generator in self._task_job_generators
        )

    def add_task(self, task: TaskModule | TaskWorkflow):
        """Add a task to the action plan, raise an error if the given task is concurrent with any existing Task
        :param task: Task to add
        :type task: Task
        """
        if self.has_task_concurrent_with(task):
            raise ValueError(
                f"Trying to add task {task} which is concurrent to existing tasks in Action plan {self.parameters.name}."
            )

        task_generator = self._resolve_task(task)
        self._raw_tasks.append(task)
        self._task_job_generators.append(task_generator)

    def _rebuild(self, previous_context: ContextParameters, attempted_context: ContextParameters) -> None:
        """Re-resolve every step already added to this workflow against the attempted context.

        If re-resolving fails (e.g. it produces invalid parameters), raise `UseContextError` (built from `previous_context` and `attempted_context`)
        and leave this workflow entirely unchanged.

        :raises UseContextError: if a step can no longer be resolved with the new context.
        """
        new_generators: list[TaskJobsGenerator] = []
        for task in self._raw_tasks:
            try:
                generator = self._resolve_task(task)
            except Exception as exc:
                raise UseContextError(
                    f"Task {task.name!r}: could not be re-resolved with the new context ({exc})",
                    job_name=task.name,
                    previous_context=previous_context,
                    attempted_context=attempted_context,
                    original_error=exc,
                ) from exc
            new_generators.append(generator)
        self._task_job_generators = new_generators

    def _resolve_task(self, task: TaskModule | TaskWorkflow) -> TaskJobsGenerator:
        """Build the TaskJobsGenerator for a single task, resolving its parameters against this
        action plan's current context.

        :raises ValueError: if `task` is of an unsupported type.
        """
        root_run_dir = self.parameters.resolve_path(self.parameters.output_dir) / task.name

        _TASK_RESOLVER = {
            TaskModule: self._resolve_task_module,
            TaskWorkflow: self._resolve_task_workflow,
        }

        resolver = _TASK_RESOLVER.get(type(task))
        if resolver is None:
            raise ValueError(f"Unknown type {type(task)} when resolving {task} for Action Plan {self}")

        return resolver(task, root_run_dir)

    def _resolve_task_module(self, task: TaskModule, root_run_dir: Path) -> ModuleTaskJobsGenerator:
        """Resolve a task, that run a module, into its ModuleTaskJobsGenerator
        :param task: task that run a module
        :type task: TaskModule
        :param root_run_dir: path to the root run tree used for the task
        :type root_run_dir: Path
        """
        if isinstance(task.parameters, (str, Path)):
            path = task.parameters if isinstance(task.parameters, Path) else Path(task.parameters)
            task_parameters = task.module.value.get_parameters_class().from_file(
                self.parameters.resolve_path(path), self._context_with_disregarded_temporal_defaults()
            )
        elif isinstance(task.parameters, dict):
            task_parameters = task.module.value.get_parameters_class().from_dict(
                task.parameters, self._context_with_disregarded_temporal_defaults()
            )
        else:
            task_parameters = self.parameters.context.apply_on_parameters(task.parameters)

        return ModuleTaskJobsGenerator(task, task_parameters, root_run_dir)

    def _resolve_task_workflow(self, task: TaskWorkflow, root_run_dir: Path) -> WorkflowTaskJobsGenerator:
        """Resolve a task, that run a workflow, into its WorkflowTaskJobsGenerator
        :param task: task that run a workflow
        :type task: TaskWorkflow
        :param root_run_dir: path to the root run tree used for the task
        :type root_run_dir: Path
        """
        if isinstance(task.workflow, (str, Path)):
            task_parameters = WorkflowParameters.from_file(
                self.parameters.resolve_path(Path(task.workflow)), self.parameters.context
            )
        elif isinstance(task.workflow, dict):
            task_parameters = WorkflowParameters.from_dict(task.workflow, self.parameters.context)
        else:
            task_parameters = self.parameters.context.apply_on_parameters(task.workflow.parameters)

        return WorkflowTaskJobsGenerator(task, task_parameters, root_run_dir)

    @property
    def jobs(self) -> Iterator[ActionPlanJob]:
        """
        Generate and return the action plan jobs.

        :return: The list of ActionPlanJob instances.
        """
        TaskGeneratorTracker = namedtuple("TaskGeneratorTracker", ["priority", "iteration", "generator"])

        priority_queue: list[TaskGeneratorTracker] = []
        for task_generator in self._task_job_generators:
            heapq.heappush(
                priority_queue,
                TaskGeneratorTracker(priority=task_generator.priority(1), iteration=1, generator=task_generator),
            )

        while len(priority_queue) > 0:
            _, current_iteration, job_generator = heapq.heappop(priority_queue)
            jobs = job_generator.build_jobs(current_iteration)
            if jobs is None:
                continue
            for job in jobs:
                yield cast(ActionPlanJob, job)
            next_iteration = current_iteration + 1
            if job_generator.is_valid_iteration(next_iteration):
                heapq.heappush(
                    priority_queue,
                    TaskGeneratorTracker(
                        priority=job_generator.priority(next_iteration),
                        iteration=next_iteration,
                        generator=job_generator,
                    ),
                )

    @property
    def jobs_count(self) -> int:
        return sum(itr.jobs_count() for itr in self._task_job_generators)

    def __repr__(self) -> str:
        """Return a human-readable string representation of the action plan."""
        return f"ActionPlan '{self.parameters.name}' ({len(self.parameters.tasks)} task{'s' if len(self.parameters.tasks) > 1 else ''} with a total of {self.jobs_count} step{'s' if self.jobs_count > 1 else ''})"

    def _context_with_disregarded_temporal_defaults(self) -> ContextParameters:
        """Return this action plan's context with a placeholder temporal block (start_date,
        end_date, execution_date) added as a low-priority default.

        Note: These three fields are always overwritten per-iteration before a Module actually runs,
        so this lets its parameters file omit the `temporal` block, or any of these three fields, entirely.
        Any value already set in the file, or in this action plan's own context, still takes priority over the placeholder.
        """
        _TEMPORAL_DEFAULTS_PLACEHOLDER = {
            "temporal": {
                "start_date": "1970-01-01 00:00:00",
                "end_date": "1970-01-01 00:00:00",
                "execution_date": "1970-01-01 00:00:00",
            }
        }
        default = deep_update(
            _TEMPORAL_DEFAULTS_PLACEHOLDER, self.parameters.context.default, override=True, inplace=False
        )
        return ContextParameters(default=default, forced=self.parameters.context.forced)
