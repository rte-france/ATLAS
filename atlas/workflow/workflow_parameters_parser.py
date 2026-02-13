"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel


class Step(BaseModel):
    """Definition of a single step in the workflow.

    :param name: Unique name identifying the step.
    :type name: str
    :param parameters_path: Path to the parameters file for the step.
    :type parameters_path: str
    """

    name: str
    parameters_path: Path


class WorkflowParameters(BaseModel):
    """Parameters for the workflow.
    :param name: Name of the workflow
    :type name: str
    :param dataset_path: Path of the Dataset to use in the workflow
    :type dataset_path: str
    :param steps: List of steps in the workflow.
    :type steps: list[Step]
    """

    dataset_path: Path
    steps: dict[str, Step]
    output_dataset_path: Path
    name: str | None = None
    generic_module_parameters_path: str | None = None


class WorkflowParametersParser:
    """A class used to parse the parameters file of a workflow"""

    @classmethod
    def from_file(cls, file_path: str | Path) -> WorkflowParameters:
        """Load parameters from a YAML file.

        :param file_path: Path to the parameters file.
        :type file_path: str or pathlib.Path
        :return: A WorkflowParameters object containing the parsed and validated parameters.
        :rtype: WorkflowParameters
        :raises ValueError: If the file extension is not supported.
        """
        file_extension = Path(file_path).suffix

        if file_extension in (".yaml", ".yml"):
            parameters = cls._parse_yaml(file_path)
        else:
            raise ValueError(f"Unsupported file extension: {file_extension}")

        return WorkflowParameters.model_validate(parameters)

    @staticmethod
    def _parse_yaml(file_path: str | Path) -> dict:
        """Parse a YAML file and return its contents as a dictionary.

        :param file_path: Path to the YAML file.
        :type file_path: str or pathlib.Path
        :return: Parsed parameters.
        :rtype: dict
        """
        with open(Path(file_path)) as file:
            return yaml.safe_load(file)
