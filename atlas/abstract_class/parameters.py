"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractModuleParameters
"""

from pathlib import Path
from typing import TypeVar

from pydantic import ConfigDict

from atlas.io_utils.parameters import DateParameters, OutputParameters, Parameters


class AbstractModuleParameters(Parameters):
    """Base class for parameters, to be extended by concrete implementations.

    :param temporal: Parameters object containing date / timestep parameters
    :type temporal: DateParameters
    :param output: Parameters object containing output path / boolean on export to do
    :type output: OutputParameters
    :param relative_src: Source for the relative path
    :type relative_src: Path
    """

    ConfigDict(arbitrary_types_allowed=True)

    temporal: DateParameters
    output: OutputParameters = OutputParameters()
    relative_src: Path = Path()

    def get_path(self, relative_path: Path) -> Path:
        return self.relative_src / relative_path

    def _get_output_dir(self) -> Path:
        return self.get_path(self.output.output_dir)

    def get_output_results_dir(self) -> Path:
        return self._get_output_dir() / "results"

    def get_output_dataset_dir(self) -> Path:
        return self._get_output_dir() / "output_dataset"

    def get_lp_dir(self) -> Path:
        return self._get_output_dir() / "lp_export"


P = TypeVar("P", bound=AbstractModuleParameters)
