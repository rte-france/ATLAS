"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
Module that implements Parameters
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Self

import yaml
from pendulum import Duration
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.enums import SolverEnum
from atlas.validators import convert_to_duration


class Parameters(BaseModel):
    """A class to parse parameters from a YAML or JSON file."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    @classmethod
    def from_file(cls, file_path: str | Path) -> Self:
        """Load parameters from a YAML or JSON file.
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


class DateParameters(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    start_date: DateTime
    end_date: DateTime
    execution_date: DateTime
    timestep: Duration = Field(
        default_factory=lambda: Duration(minutes=60), description="Discretization job of the simulated time interval"
    )

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        """Validation of start, end and execution date

        :raises ValueError: If the start, end and execution date are not coherent
        :return: The AbstractModuleParameters if dates are validate
        :rtype: AbstractModuleParameters
        """
        if self.end_date < self.start_date:
            raise ValueError(
                f"Start date '{self.start_date.to_datetime_string()}' must be previous "
                f"to end date '{self.end_date.to_datetime_string()}'"
            )
        return self

    @field_validator(
        "timestep",
        mode="before",
    )
    @classmethod
    def parse_duration(cls, v):
        """Convert various duration formats to Duration objects."""
        return convert_to_duration(v)


class SolverParameters(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    solver_name: SolverEnum = SolverEnum.XPRESS
    export_lp: bool = False
    use_presolve: bool = False
    duality_gap: float = Field(0.0001, description="duality gap used for the optimization.")
    timeout: Duration = Field(default_factory=lambda: Duration(minutes=4), description="Timeout of the optimization.")

    @field_validator("timeout", mode="before")
    @classmethod
    def parse_timeout(cls, v):
        """Convert various duration formats to Duration objects."""
        return convert_to_duration(v)


class MultiProcessingParameters(BaseModel):
    enable: bool = False
    max_workers: int | None = None


class OutputParameters(BaseModel):
    export_result: bool = False
    export_output_dataset: bool = False
    output_dir: Path = Path("output")
