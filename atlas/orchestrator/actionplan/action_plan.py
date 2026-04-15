"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.orchestrator.actionplan.job import ActionPlanJob
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters, Task
from atlas.orchestrator.actionplan.task_manager import TaskListIterator


class ActionPlan(AbstractOrchestrator[ActionPlanParameters, ActionPlanJob]):
    """A structure for managing the sequential execution of multiple modules and workflow through a list of action plan steps.

    Each job processes the output of the previous one, starting from the input dataset."""

    def __init__(self, parameters: ActionPlanParameters):
        """Initialize a Workflow instance.

        :param parameters: Name of the workflow.
        :type parameters: WorkflowParameters
        """
        self.parameters = parameters
        self.tasks: list[Task] = parameters.tasks

    @classmethod
    def from_file(cls, file_path: str | Path) -> ActionPlan:
        file_path = Path(file_path)
        parameters = ActionPlanParameters.from_file(file_path=file_path)
        parameters._orchestrator_path = file_path.parent
        return cls(parameters=parameters)

    @property
    def jobs(self) -> Iterator[ActionPlanJob]:
        """
        Access the action plan jobs.

        :return: The list of ActionPlanJob instances.
        """
        for task, datetime in TaskListIterator(self.tasks):
            yield from task.associated_jobs_with_execution_date(datetime)

    @property
    def jobs_count(self) -> int:
        raise NotImplementedError

    def __repr__(self) -> str:
        """Return a human-readable string representation of the workflow."""
        task_count = 0  # FIXME
        return f"ActionPlan '{self.parameters.name}' ({task_count} task{'s' if task_count != 1 else ''} with a total of {self.jobs_count()} step{'s' if len(self.jobs_count()) != 1 else ''})"
