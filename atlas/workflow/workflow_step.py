"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.abstract_class.abstract_parameters import AbstractParameters


class WorkflowStep:
    """
    A step in a workflow, responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __init__(
        self,
        name: str,
        module_parameters: AbstractParameters,
        module: AbstractModule,
        input_dataset: AbstractDataset | None = None,
    ):
        """
        Initialize a WorkflowStep.

        :param name: Name of the workflow step.
        :param module_parameters: Parameters for the module execution.
        :param module: Module to be executed in this step.
        :param input_dataset: Input dataset for the module, optional.
        """
        self.name: str = name
        self.module: AbstractModule = module
        self.module_parameters: AbstractParameters = module_parameters
        self.input_dataset: AbstractDataset | None = input_dataset
        self._output_dataset: AbstractDataset | None = None

    @property
    def output_dataset(self) -> AbstractDataset | None:
        """
        Output dataset produced after executing the step.

        :return: An AbstractDataset or None if not yet executed.
        """
        return self._output_dataset

    def get_output_dataset(self) -> AbstractDataset | None:
        """
        Get the output dataset produced by this workflow step.

        :return: An AbstractDataset or None if not yet executed.
        """
        return self._output_dataset

    def execute(self) -> None:
        """
        Execute the step's module with the given parameters and input dataset.
        Stores the resulting dataset as output.
        """
        self._output_dataset = self.module.execute(self.module_parameters, self.input_dataset)
