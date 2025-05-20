"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.workflow.workflow_step import WorkflowStep


class Workflow:
    """A structure designed to allow the sequential execution of multiple modules through a list of steps."""

    def __init__(self, name: str, dataset: AbstractDataset, steps: list[WorkflowStep] | None):
        self.name = name
        self.dataset = dataset
        if steps is None:
            self.steps = []
        else:
            self.steps = steps

    def add_step(self, step: WorkflowStep) -> None:
        """
        Add one step at the end of the workflow
        :param step: a WorkflowStep
        :return:
        """
        self.steps.append(step)

    def add_steps(self, steps: list[WorkflowStep]) -> None:
        """
        Add a list of WorkflowStep at the end of the workflow
        :param steps: a list of WorkflowStep
        :return:
        """
        self.steps.extend(steps)

    def get_output_dataset(self) -> AbstractDataset | None:
        """Returns the final dataset of the workflow"""
        return self.steps[-1].get_output_dataset()

    def execute(self) -> None:
        """
        Execute the workflow
        :return:
        """
        output_dataset = None
        first = True
        for step in self.steps:
            if first:
                first = False
                step.input_dataset = self.dataset
                step.execute_step()
                output_dataset = step.output_dataset
            else:
                step.input_dataset = output_dataset
                step.execute_step()
