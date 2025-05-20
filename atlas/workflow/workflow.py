"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.workflow.workflow_step import WorkflowStep


class Workflow:
    """A structure for managing the sequential execution of multiple modules through a list of workflow steps.

    Each step processes the output of the previous one, starting from the input dataset."""

    def __init__(self, name: str, dataset: AbstractDataset, steps: list[WorkflowStep] | None):
        """Initialize a Workflow instance.

        :param name: Name of the workflow.
        :type name: str
        :param dataset: The initial input dataset for the workflow.
        :type dataset: AbstractDataset
        :param steps: Optional list of workflow steps to execute.
        :type steps: list[WorkflowStep] | None
        """
        self.name = name
        self.dataset = dataset
        self._steps: list[WorkflowStep] = steps if steps is not None else []

    @property
    def steps(self) -> list[WorkflowStep]:
        """
        Access the workflow steps.

        :return: The list of WorkflowStep instances.
        """
        return self._steps

    def add_step(self, step: WorkflowStep) -> None:
        """Add a single step to the end of the workflow."""
        self._steps.append(step)

    def add_steps(self, steps: list[WorkflowStep]) -> None:
        """Add multiple steps to the end of the workflow."""
        self._steps.extend(steps)

    def get_output_dataset(self) -> AbstractDataset | None:
        """Returns the final dataset of the workflow"""
        return self.steps[-1].get_output_dataset()

    def execute(self) -> None:
        """
        Execute the workflow
        :return:
        """
        """
        Execute all workflow steps sequentially.

        Each step receives as input the output of the previous step.
        The first step receives the workflow's initial dataset.
        """
        output_dataset: AbstractDataset | None = None
        for i, step in enumerate(self.steps):
            step.input_dataset = self.dataset if i == 0 else output_dataset
            step.execute()
            output_dataset = step.output_dataset
