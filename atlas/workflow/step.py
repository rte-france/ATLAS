"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from atlas import AtlasDataset
from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.modules.day_ahead_orders.module import DayAheadOrdersModule
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule


class ModuleRegistry(Enum):
    """Registry mapping module names to their implementation classes."""

    MarketClearing = MarketClearingModule
    PortfolioOptimisation = PortfolioOptimisationModule
    DayAheadOrders = DayAheadOrdersModule

    @classmethod
    def get(cls, name: str) -> type[AbstractModule]:
        try:
            return cls[name].value
        except KeyError:
            valid = [m.name for m in cls]
            raise ValueError(f"Unknown module: '{name}'. Valid modules are: {valid}") from None


class Step(BaseModel):
    """Definition of a single step in the workflow.

    :param name: Name identifying the step. Defaults to the module name if not provided.
    :type name: str
    :param parameters_path: Path to the parameters file for the step.
    :type parameters_path: str
    """

    name: str | None = None
    module: ModuleRegistry
    parameters_path: Path

    @field_validator("module", mode="before")
    @classmethod
    def coerce_module(cls, v: Any) -> ModuleRegistry:
        if isinstance(v, str):
            return ModuleRegistry(ModuleRegistry.get(v))
        return v

    @model_validator(mode="after")
    def set_default_name(self) -> Step:
        if self.name is None:
            self.name = self.module.name
        return self


class WorkflowStep:
    """
    A step in a workflow, responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __init__(self, name: str, module: type[AbstractModule], parameters: dict[str, Any]):
        """
        Initialize a WorkflowStep.

        :param name: Name of the workflow step.
        :type name: str
        :param module: Module to be executed in this step.
        :type module: AbstractModule
        :param parameters: Parameter dict for the module.
        :type parameters: dict[str, Any]
        """
        self.name: str = name
        self.module = module()
        self.parameters = parameters
        self._output_dataset: AbstractModuleOutput | None = None

    @property
    def output_dataset(self) -> AbstractModuleOutput | None:
        """
        Output dataset produced after executing the step.

        :return: An AbstractDataset or None if not yet executed.
        """
        return self._output_dataset

    def get_output_dataset(self) -> AbstractModuleOutput | None:
        """
        Get the output dataset produced by this workflow step.

        :return: An AbstractDataset or None if not yet executed.
        """
        return self._output_dataset

    def run(self, input_dataset: AtlasDataset) -> None:
        """
        Execute the step's module with the given parameters and input dataset.
        Stores the resulting dataset as output.
        """
        self._output_dataset = self.module.run(input_dataset, self.parameters)

    def __repr__(self) -> str:
        """Return a detailed string representation of the workflow step."""
        module_name = self.module.__class__.__name__
        has_output = self._output_dataset is not None
        return f"WorkflowStep(name={self.name!r}, module={module_name}, executed={has_output})"

    def __str__(self) -> str:
        """Return a human-readable string representation of the workflow step."""
        return f"WorkflowStep '{self.name}' ({self.module.__class__.__name__})"
