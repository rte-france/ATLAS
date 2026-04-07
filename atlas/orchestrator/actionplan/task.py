"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import Any

from atlas.orchestrator.actionplan.step import ActionPlanStep


class ActionPlanTask:
    """
    A task in a workflow
    """

    def __init__(self, parameters: dict[str, Any]):
        """
        Initialize an ActionPlanStep.

        :param name: Name of the action plan step.
        :type name: str
        :param module: Module to be executed (if any) in this step.
        :type module: AbstractModule
        :param workflow: Workflow to be executed (if any) in this step.
        :type workflow: string
        :param priority: Priority of the action plan step.
        :type priority: int
        :param from_: First date time to execute this step.
        :type from_: DateTime
        :param until: Last date time to execute this step.
        :type until: DateTime
        :param frequency: Frequency of the action plan step.
        :type frequency: Duration
        """
        raise NotImplementedError

    def generate_steps(self) -> list[ActionPlanStep]:
        """
        Associated step to the given task.

        :return: The list of steps the task require to execute.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow task."""
        raise NotImplementedError
