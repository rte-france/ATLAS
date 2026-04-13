"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from atlas.abstract_class.orchestrator_parameters import AbstractOrchestratorParameters
from atlas.orchestrator.actionplan.job import Task
from atlas.orchestrator.hook.hook import Hook


class ActionPlanParameters(AbstractOrchestratorParameters):
    """Parameters for the action plan.
    :param tasks: List of tasks to execute
    :type tasks: list[Task]
    :param hooks: List of hooks in the workflow
    :type hooks: list[Hook]
    """

    tasks: list[Task]
    hooks: list[Hook]
