"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel


class Parameters(BaseModel):
    dataset_path: str


class Step(BaseModel):
    name: str
    parameters_path: str


class WorkflowParameters(BaseModel):
    parameters: Parameters
    steps: dict[str, Step]


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

        return WorkflowParameters(**parameters)

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
