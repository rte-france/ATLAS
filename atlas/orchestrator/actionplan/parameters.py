"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from atlas.io_utils.parameters import Parameters
from atlas.orchestrator.actionplan.task import ActionPlanTask
from atlas.orchestrator.hook.hook import Hook


class ActionPlanParameters(Parameters):
    """Parameters for the action plan.
    :param name: Name of the action plan
    :type name: str
    :param tasks: List of tasks to execute
    :type tasks: list[Tasks]
    :param hooks: List of hooks in the workflow
    :type hooks: list[Hook]
    """

    name: str | None = None
    tasks: list[ActionPlanTask]
    hooks: list[Hook]

