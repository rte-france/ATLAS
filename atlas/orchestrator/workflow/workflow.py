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
from atlas.config import logger
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.handler.cis_handler import CISHandler
from atlas.orchestrator.workflow.parameters import WorkflowParameters
from atlas.orchestrator.workflow.step import WorkflowStep
from atlas.timing import timer


class Workflow(AbstractOrchestrator):
    """A structure for managing the sequential execution of multiple modules through a list of workflow steps.

    Each step processes the output of the previous one, starting from the input dataset."""

    def __init__(self, parameters: WorkflowParameters, workflow_path: Path):
        """Initialize a Workflow instance.

        :param parameters: Name of the workflow.
        :type parameters: WorkflowParameters
        :param workflow_path: Path.
        :type workflow_path: WorkflowParameters
        """
        self.parameters = parameters
        self.workflow_path = workflow_path
        self.generic_module_parameters: dict[str, Any] = {}
        self._steps: list[WorkflowStep] = []

        self.build_generic_module_parameters()
        self.build_steps()

    @classmethod
    def from_file(cls, file_path: str | Path) -> Workflow:
        file_path = Path(file_path)
        parameters = WorkflowParameters.from_file(file_path=file_path)
        workflow_path = file_path.parent if parameters.path_from_workflow else Path()
        return cls(parameters=parameters, workflow_path=workflow_path)

    def build_generic_module_parameters(self):
        if self.parameters.parameters_path:
            with open(self.workflow_path / self.parameters.parameters_path) as file:
                self.generic_module_parameters = yaml.safe_load(file)

    @staticmethod
    def add_index_in_step_name(steps: list) -> None:
        """Append a numeric index suffix to duplicate step names, in-place.

        Steps whose name is unique are left unchanged. Steps sharing a name are
        renamed '<name>_1', '<name>_2', etc., in the order they appear.

        :param steps: List of step parameter objects exposing a 'name' attribute.
        :type steps: list
        """
        name_counts: dict[str, int] = {}
        for step in steps:
            name_counts[step.name] = name_counts.get(step.name, 0) + 1

        name_index: dict[str, int] = {}
        for step in steps:
            if name_counts[step.name] > 1:
                name_index[step.name] = name_index.get(step.name, 0) + 1
                step.name = f"{step.name}_{name_index[step.name]}"

    def build_steps(self):
        self.add_index_in_step_name(self.parameters.steps)

        for step in self.parameters.steps:
            parameters = Workflow.build_module_parameters(
                self.generic_module_parameters, self.workflow_path / step.parameters_path
            )
            if "output" not in parameters:
                parameters["output"] = {}
            parameters["output"]["output_dir"] = self.workflow_path / self.parameters.output_dir / step.name
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

    def execute(self) -> None:
        """
        Execute the workflow

        Execute all workflow steps sequentially.

        Each step receives as input the output of the previous step.
        The first step receives the workflow's initial dataset.
        """
        logger.info(f"Launching workflow : {self.parameters.name}")
        atlas_dataset = AtlasDataset.from_directory(self.workflow_path / self.parameters.dataset_path)
        cis = CurrentInputState(atlas_dataset)

        for step in self.steps:
            logger.info(f"Launching step :'{step.name}'")
            input_dataset = cis.filter_dataset(step.module.get_business_model_class_used(), step.module.get_filters())

            with timer() as t:
                step.run(input_dataset)
            logger.info(f"Step '{step.name}' completed in {t()} seconds")

            output_dataset = step.output_dataset

            if not output_dataset:
                raise RuntimeError(f"Step {step.name} did not produce output_dataset")

            logger.debug("Applying all change sets to the current input state")
            CISHandler.apply(output_dataset.change_sets, cis)
            if step.parameters.output.export_output_dataset:
                cis.to_directory(step.parameters.get_path(step.parameters.output.output_dir) / "output_dataset")

            logger.info(f"Finishing step :'{step.name}'")

        if self.parameters.export_output:
            cis.to_directory(self.workflow_path / self.parameters.output_dir / "workflow_output")
