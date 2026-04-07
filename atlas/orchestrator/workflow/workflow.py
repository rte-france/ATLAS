"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.abstract_class.abstract_orchestrator import AbstractOrchestrator
from atlas.orchestrator.workflow.parameters import WorkflowParameters
from atlas.orchestrator.workflow.step import WorkflowStep


class Workflow(AbstractOrchestrator[WorkflowParameters, WorkflowStep]):
    """A structure for managing the sequential execution of multiple modules through a list of workflow steps.

    Each step processes the output of the previous one, starting from the input dataset."""

    def __init__(self, parameters: WorkflowParameters):
        """Initialize a Workflow instance.

        :param parameters: Name of the workflow.
        :type parameters: WorkflowParameters
        """
        self.parameters = parameters
        self.generic_module_parameters: dict[str, Any] = {}
        self._steps: list[WorkflowStep] = []

        self.build_generic_module_parameters()
        self.build_steps()

    @classmethod
    def from_file(cls, file_path: str | Path) -> Workflow:
        file_path = Path(file_path)
        parameters = WorkflowParameters.from_file(file_path=file_path)
        parameters._orchestrator_path = file_path.parent
        return cls(parameters=parameters)

    def build_generic_module_parameters(self):
        if self.parameters.parameters_path:
            with open(self.parameters.resolve_path(self.parameters.parameters_path)) as file:
                self.generic_module_parameters = yaml.safe_load(file)

    def build_steps(self):
        WorkflowStep.add_index_in_step_name(self.parameters.steps)

        for step in self.parameters.steps:
            parameters = Workflow.build_module_parameters(
                self.generic_module_parameters, self.parameters.resolve_path(step.parameters_path)
            )
            if "output" not in parameters:
                parameters["output"] = {}
            parameters["output"]["output_dir"] = self.parameters.resolve_path(self.parameters.output_dir) / step.name
            workflow_step = WorkflowStep(step.name, step.module.value, parameters)
            self.add_step(workflow_step)

    @staticmethod
    def build_module_parameters(parameters: dict[str, Any], parameters_path: Path) -> dict[str, Any]:
        parameters = copy.deepcopy(parameters)
        with open(parameters_path) as file:
            custom_parameters = yaml.safe_load(file)
        parameters.update(custom_parameters)
        return parameters

    @property
    def steps(self) -> list[WorkflowStep]:
        """
        Access the workflow steps.

        :return: The list of WorkflowStep instances.
        """
        return self._steps

    def add_step(self, step: WorkflowStep | list[WorkflowStep]) -> None:
        """Add one or multiple steps to the end of the workflow."""
        if isinstance(step, list):
            if not all(isinstance(s, WorkflowStep) for s in step):
                raise TypeError("All items in the list must be WorkflowStep instances.")
            self._steps.extend(step)
        else:
            if not isinstance(step, WorkflowStep):
                raise TypeError(f"Expected a WorkflowStep instance, got {type(step).__name__}.")
            self._steps.append(step)

    def get_output_dataset(self) -> AbstractDataset | None:
        """Returns the final dataset of the workflow"""
        return self.steps[-1].get_output_dataset()

    def __repr__(self) -> str:
        """Return a human-readable string representation of the workflow."""
        step_count = len(self._steps)
        return f"Workflow '{self.parameters.name}' ({step_count} step{'s' if step_count != 1 else ''})"
