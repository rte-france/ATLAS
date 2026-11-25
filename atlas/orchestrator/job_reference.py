"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskRef:
    """
    Action plan task a job belongs to.

    :param name: Name of the task.
    :type name: str
    :param iteration: Iteration number of the task, starting at 1.
    :type iteration: int
    """

    name: str
    iteration: int


@dataclass(frozen=True)
class StepRef:
    """
    Workflow step a job runs.

    :param name: Name of the step, without any job name prefix.
    :type name: str
    :param is_first: Whether the step is the first one of its workflow.
    :type is_first: bool
    :param is_last: Whether the step is the last one of its workflow.
    :type is_last: bool
    """

    name: str
    is_first: bool
    is_last: bool
