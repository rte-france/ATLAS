"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractParameters
"""

import json
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, model_validator
from pydantic_extra_types.pendulum_dt import DateTime
from typing_extensions import Self

from atlas.enum import SolverEnum


class AbstractParameters(BaseModel):
    """Base class for parameters, to be extended by concrete implementations.

    :param start_date: Study start date
    :type start_date: datetime
    :param end_date: Study end date
    :type end_date: datetime
    :param execution_date: Study execution date
    :type execution_date: datetime
    :param export_result: true if result should be export else false
    :type export_result: bool
    :param export_output_dataset: true if business model object output should be export else false
    :type export_output_dataset: bool
    """

    start_date: DateTime
    end_date: DateTime
    execution_date: DateTime
    export_result: bool = True
    export_output_dataset: bool = False
    solver_name: SolverEnum = SolverEnum.XPRESS

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        """Validation of start, end and execution date

        :raises ValueError: If the start, end and execution date are not coherent
        :return: The AbstractParameters if dates are validate
        :rtype: AbstractParameters
        """

        if self.end_date < self.start_date:
            raise ValueError(
                f"Start date '{self.start_date.to_datetime_string()}' must be inferior "
                f"to end date '{self.end_date.to_datetime_string()}'"
            )
        return self

    @classmethod
    def from_file(cls, file_path: str | Path) -> Self:
        """
        Load parameters from a YAML or JSON file.
        :param file_path: Path to the parameters file.
        :type file_path: str or pathlib.Path
        :return: A Parameters object containing the parsed and validated parameters.
        :rtype: Parameters
        :raises ValueError: If the file extension is not supported.
        """
        file_extension = Path(file_path).suffix

        if file_extension in (".yaml", ".yml"):
            parameters = cls._parse_yaml(file_path)
        elif file_extension == ".json":
            parameters = cls._parse_json(file_path)
        else:
            raise ValueError(f"Unsupported file extension: {file_extension}")

        return cls(**parameters)

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

    @staticmethod
    def _parse_json(file_path: str | Path) -> dict:
        """Parse a JSON file and return its contents as a dictionary.
        :param file_path: Path to the JSON file.
        :type file_path: str or pathlib.Path
        :return: Parsed parameters.
        :rtype: dict
        """
        with open(Path(file_path)) as file:
            return json.load(file)


module_parameters_type_var = TypeVar("module_parameters_type_var", bound=AbstractParameters)
