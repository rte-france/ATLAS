"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from atlas.abstract_class.dataset import AbstractModuleOutput
from atlas.abstract_class.module import AbstractModule
from atlas.abstract_class.parameters import AbstractModuleParameters
from atlas.io_utils.atlas_dataset import AtlasDataset


class AbstractJob:
    """
    A job in an orchestrator, responsible for executing a module using provided parameters
    and producing an output dataset from an input dataset.
    """

    def __init__(
        self,
        name: str,
        module: type[AbstractModule],
        parameters: dict[str, Any] | str | Path | AbstractModuleParameters,
    ):
        """
        Initialize an AbstractJob.

        :param name: Name of the job.
        :type name: str
        :param module: Module to be executed in this job.
        :type module: AbstractModule
        :param parameters: Typed parameters ; raw dict ; path to parameter file ; will be validated via the module's parameters class.
        :type parameters: dict or str or Path or AbstractModuleParameters
        """
        self.name: str = name
        self.module = module()
        if isinstance(parameters, AbstractModuleParameters):
            self.parameters = parameters
        else:
            self.parameters = self.module.import_parameters(parameters)
        self._output_dataset: AbstractModuleOutput | None = None

    @property
    def output_dataset(self) -> AbstractModuleOutput | None:
        """
        Output dataset produced after executing the job.

        :return: An AbstractDataset or None if not yet executed.
        """
        return self._output_dataset

    def get_output_dataset(self) -> AbstractModuleOutput | None:
        """
        Get the output dataset produced by this orchestrator job.

        :return: An AbstractDataset or None if not yet executed.
        """
        return self._output_dataset

    def run(self, input_dataset: AtlasDataset) -> None:
        """
        Execute the job's module with the given parameters and input dataset.
        Stores the resulting dataset as output.
        """
        self._output_dataset = self.module.run(input_dataset, self.parameters)


J = TypeVar("J", bound=AbstractJob)
