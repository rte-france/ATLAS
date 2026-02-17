"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import copy
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from atlas.abstract_class.abstract_dataset import AbstractDataset
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.config import logger
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule
from atlas.workflow.current_input_state import CurrentInputState
from atlas.workflow.handler.cis_handler import CISHandler
from atlas.workflow.workflow_parameters import Step, WorkflowParameters
from atlas.workflow.workflow_step import WorkflowStep


class ModuleRegistry(Enum):
    """Registry mapping module names to their implementation classes."""

    MarketClearing = MarketClearingModule
    PortfolioOptimisation = PortfolioOptimisationModule

    @classmethod
    def get(cls, name: str) -> type[AbstractModule]:
        try:
            return cls[name].value
        except KeyError:
            valid = [m.name for m in cls]
            raise ValueError(f"Unknown module: '{name}'. Valid modules are: {valid}") from None


class Workflow:
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
        parameters = WorkflowParameters.from_file(file_path=file_path)
        return cls(parameters=parameters)

    def build_generic_module_parameters(self):
        if self.parameters.generic_module_parameters_path:
            with open(self.parameters.generic_module_parameters_path) as file:
                self.generic_module_parameters = yaml.safe_load(file)

    def build_steps(self):
        for step in self.parameters.steps:
            self.build_step(step)

    def build_step(self, step: Step):
        module = ModuleRegistry.get(step.name)
        parameters = Workflow.build_module_parameters(self.generic_module_parameters, step.parameters_path)

        workflow_step = WorkflowStep(step.name, module, parameters)
        self.add_step(workflow_step)

    @staticmethod
    def build_module_parameters(parameters: dict[str, Any], parameters_path: Path):
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
        str_name = f" : '{self.parameters.name}'" if self.parameters.name else ""
        logger.debug(f"Launching workflow{str_name}")
        atlas_dataset = AtlasDataset.from_directory(self.parameters.dataset_path)
        cis = CurrentInputState(atlas_dataset)

        for step in self.steps:
            logger.debug(f"Launching step :'{step.name}'")
            input_dataset = cis.filter_dataset(step.module.get_business_model_class_used(), step.module.get_filters())
            # Before hook
            step.run(input_dataset)
            # After hook
            output_dataset = step.output_dataset
            assert output_dataset is not None, f"Step {step.name} did not produce output_dataset"
            change_sets = output_dataset.change_sets

            logger.debug("Applying list of change set")
            CISHandler.apply(change_sets, cis)
            logger.debug(f"Finishing step :'{step.name}'")

        cis.data.to_directory(self.parameters.output_dataset_path)
