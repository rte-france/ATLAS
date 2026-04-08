"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.abstract_class.abstract_orchestrator import AbstractOrchestrator
from atlas.orchestrator.actionplan.job import ActionPlanJob
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters
from atlas.orchestrator.current_input_state import CurrentInputState


# FIXME this class is similar to Workflow class, common part must be refactored in AbstractOrchestrator class
class ActionPlan(AbstractOrchestrator):
    """A structure for managing the sequential execution of multiple modules and workflow through a list of action plan steps.

    Each job processes the output of the previous one, starting from the input dataset."""

    def __init__(self, parameters: ActionPlanParameters, action_plan_path: Path):
        """Initialize a Workflow instance.

        :param parameters: Name of the workflow.
        :type parameters: WorkflowParameters
        """
        raise NotImplementedError

    def build_steps(self):
        raise NotImplementedError

    @property
    def jobs(self) -> list[ActionPlanJob]:
        raise NotImplementedError

    def add_step(self, step: ActionPlanJob | list[ActionPlanJob]) -> None:
        raise NotImplementedError

    def get_output_dataset(self) -> AbstractDataset | None:
        raise NotImplementedError

    def __repr__(self) -> str:
        raise NotImplementedError

    def execute(self) -> CurrentInputState:
        raise NotImplementedError
