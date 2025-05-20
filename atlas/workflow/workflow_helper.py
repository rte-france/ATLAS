"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.workflow.workflow import Workflow
from atlas.workflow.workflow_step import WorkflowStep


class WorkflowHelper:
    """Utilities for workflow objects"""

    @staticmethod
    def create_simple_workflow(
        dataset: AbstractDataset,
        module_parameters: AbstractParameters,
        module: AbstractModule,
        name: str = "wf",
    ) -> Workflow:
        """
        Create a workflow with one step
        :param name: name of the workflow
        :param dataset: the dataset
        :param module_parameters: the module parameters
        :param module: the module
        :return: the workflow
        """
        step = WorkflowStep(name + "_step1", module_parameters, module, dataset)
        return Workflow(name, dataset, [step])
