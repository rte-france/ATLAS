"""Copyright (c) 2025, RTE (www.rte-france.com)
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
Module that implements Parameters
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Self

import yaml
from pendulum import duration
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.enums import SolverEnum
from atlas.io_utils.utils import deep_update
from atlas.validators import DurationField


class Parameters(BaseModel):
    """A class to parse parameters from a YAML or JSON file."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    @classmethod
    def from_file(cls, file_path: str | Path, context: ContextParameters | None = None) -> Self:
        """Load parameters from a YAML or JSON file.
        :param file_path: Path to the parameters file.
        :type file_path: str or pathlib.Path
        :param context: Context parameters to use.
        :type context: dict
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

        return cls.from_dict(parameters, context)

    @classmethod
    def from_dict(cls, parameters: dict | None, context: ContextParameters | None = None) -> Self:
        """Build parameters from an in-memory dict, applying an optional context.

        :param parameters: Raw parameter values.
        :type parameters: dict or None
        :param context: Context parameters to use.
        :type context: ContextParameters or None
        :return: A Parameters object containing the parsed and validated parameters.
        :rtype: Parameters
        """
        if context is None:
            return cls(**(parameters or {}))

        if parameters is None:
            parameters = {}

        parameters = context.apply_on_dict(parameters)
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
    timestep: DurationField = Field(
        default_factory=lambda: duration(minutes=60),
        description="Discretization step of the simulated time interval",
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


class SolverParameters(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    solver_name: SolverEnum = SolverEnum.XPRESS
    export_lp: bool = False
    use_presolve: bool = False
    duality_gap: float = Field(0.0001, description="duality gap used for the optimization.")
    timeout: DurationField = Field(
        default_factory=lambda: duration(minutes=4), description="Timeout of the optimization."
    )


class MultiProcessingParameters(BaseModel):
    enable: bool = False
    max_workers: int | None = None


class OutputParameters(BaseModel):
    export_result: bool = False
    export_output_dataset: bool = False
    output_dir: Path = Path("output")


class ContextParameters(BaseModel):
    """A context contains values to use as default or to forced on corresponding parameters."""

    default: dict = Field(default_factory=lambda: {})
    forced: dict = Field(default_factory=lambda: {})

    def apply(self, context: ContextParameters, inplace: bool = True) -> ContextParameters:
        """
        Override any value in this context that are also present in given context.
        :param context: context to use for this parameter
        :type context: ContextParameters
        :param inplace: If True, modifies this object. If False, returns a deep copy with modified attributes.
        :type inplace: bool
        """
        updated_default = deep_update(self.default, context.default, override=True, inplace=inplace)
        updated_forced = deep_update(self.forced, context.forced, override=True, inplace=inplace)
        return self if inplace else ContextParameters(default=updated_default, forced=updated_forced)

    def apply_on_dict(self, base: dict, inplace: bool = False) -> dict:
        """
        Return the resulting dictionary obtained by applying this context to the given dictionary,
        return a deepcopy if inplace is False.
        Any default value in this context will be added if not present in the dictionary.
        Override any forced value from this context that are also present in given dict.
        :param base: dictionary to use as base result
        :type base: dict
        :param inplace: If True, modifies given dict. If False, returns a deep copy with modified attributes.
        :type inplace: bool
        """
        updated_dict = base if inplace else copy.deepcopy(base)
        deep_update(updated_dict, self.default, False)
        deep_update(updated_dict, self.forced, True)
        return updated_dict

    def apply_on_parameters(self, parameter: Parameters, inplace: bool = False) -> Parameters:
        """
        Copy and update parameters based on this context, return a deepcopy if deepcopy is True.
        Any default value in this context will be added if value is None in the parameter.
        Override any forced value from this context that are also present in given parameter.
        :param parameter: parameter to copy and update using this context
        :type parameter: Parameters
        :param inplace: If True, modifies given parameter. If False, returns a deep copy with modified attributes.
        :type inplace: bool
        """
        # prune self.default to field that exist and value is None
        applicable_defaults = {
            k: v for k, v in self.default.items() if hasattr(parameter, k) and getattr(parameter, k) is None
        }

        # create a copy of dict applicable_defaults, then append self.forced and override existing field
        fields_to_update = {**applicable_defaults, **self.forced}

        # prune fields_to_update to field that exist
        applicable_update = {k: v for k, v in fields_to_update if hasattr(parameter, k)}

        return parameter.model_copy(update=applicable_update, deep=inplace)
