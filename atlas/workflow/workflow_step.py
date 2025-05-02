"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.abstract_class.abstract_parameters import AbstractParameters


class WorkflowStep:
    """A step of a workflow"""

    def __init__(
        self,
        name: str,
        module_parameters: AbstractParameters,
        module: AbstractModule,
        input_dataset: AbstractDataset = None,
    ):
        self.name = name
        self.module = module
        self.module_parameters = module_parameters
        self.input_dataset = input_dataset
        self.output_dataset = None

    def execute_step(self) -> None:
        """Execute the module of this step"""
        self.output_dataset = self.module.execute(self.module_parameters, self.input_dataset)
