"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import Any

from atlas.abstract_class.abstract_job import AbstractJob


class ActionPlanJob(AbstractJob):
    """
    A job in an action plan is responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow job."""
        module_name = self.module.__class__.__name__
        has_output = self._output_dataset is not None
        return f"ActionPlanStep(name={self.name!r}, module={module_name}, executed={has_output})"


class Task:
    """
    A task in a workflow
    """

    def __init__(self, parameters: dict[str, Any]):
        """
        Initialize an ActionPlanJob.

        :param name: Name of the action plan job.
        :type name: str
        :param module: Module to be executed (if any) in this job.
        :type module: AbstractModule
        :param workflow: Workflow to be executed (if any) in this job.
        :type workflow: string
        :param priority: Priority of the action plan job.
        :type priority: int
        :param from_: First date time to execute this job.
        :type from_: DateTime
        :param until: Last date time to execute this job.
        :type until: DateTime
        :param frequency: Frequency of the action plan job.
        :type frequency: Duration
        """
        raise NotImplementedError

    def generate_steps(self) -> list[ActionPlanJob]:
        """
        Associated job to the given task.

        :return: The list of steps the task require to execute.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow task."""
        raise NotImplementedError
