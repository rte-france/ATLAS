"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements AbstractModuleParameters
"""

from pathlib import Path
from typing import TypeVar

from pydantic import ConfigDict

from atlas.io_utils.parameters import DateParameters, ExportParameters, Parameters, RunPaths


class AbstractModuleParameters(Parameters):
    """Base class for parameters, to be extended by concrete implementations.

    :param temporal: Parameters object containing date / timestep parameters
    :type temporal: DateParameters
    :param export: What the module writes to disk, and the run directory it writes into
    :type export: ExportParameters
    """

    ConfigDict(arbitrary_types_allowed=True)

    temporal: DateParameters
    export: ExportParameters = ExportParameters()

    @property
    def run_paths(self) -> RunPaths:
        """Resolved directory layout of the run this module executes in."""
        return RunPaths(self.export.run_dir)

    @property
    def results_dir(self) -> Path:
        """Directory the module writes its business CSVs into."""
        return self.run_paths.results

    @property
    def dataset_dir(self) -> Path:
        """Directory the module serializes its dataset into."""
        return self.run_paths.dataset

    @property
    def lp_dir(self) -> Path:
        """Directory the solver exports its LP files into."""
        return self.run_paths.lp_export


P = TypeVar("P", bound=AbstractModuleParameters)
