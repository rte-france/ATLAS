"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from atlas.io_utils.parameters import Parameters


class AbstractOrchestratorParameters(Parameters):
    """Parameters for the orchestrator.
    :param name: Name of the orchestrator
    :type name: str
    :param dataset_path: Path of the Dataset to use in the orchestrator
    :type dataset_path: str
    :param rollback_on_step_failure: If True, rollback CIS to previous job state when a job fails
    :type rollback_on_step_failure: bool
    :param create_step_snapshots: If True, create CIS snapshots before each job for debugging
    :type create_step_snapshots: bool
    :param path_from_orchestrator: If True, resolve relative paths from orchestrator file location
    :type path_from_orchestrator: bool
    TODO add missing parameters
    """

    name: str | None = None
    dataset_path: Path
    output_dataset_path: Path
    parameters_path: Path | None = None
    path_from_orchestrator: bool = True
    output_dir: Path = Path()
    rollback_on_step_failure: bool = True
    create_step_snapshots: bool = False
    export_output: bool = True
    _orchestrator_path: Path = Path()

    @property
    def base_path(self) -> Path:
        """Returns the workflow base path if path_from_orchestrator is True, otherwise empty Path.

        This allows paths in parameters to be either:
        - Relative (resolved from workflow file location if path_from_orchestrator=True)
        - Absolute (used as-is regardless of path_from_orchestrator)

        :return: Base path for resolving relative paths
        :rtype: Path
        """
        return self._orchestrator_path if self.path_from_orchestrator else Path()

    def resolve_path(self, path: Path) -> Path:
        """Resolve a path based on path_from_orchestrator setting.

        :param path: Path to resolve (can be relative or absolute)
        :type path: Path
        :return: Resolved path (absolute paths returned as-is, relative paths resolved from base_path)
        :rtype: Path
        """
        if path.is_absolute():
            return path
        return self.base_path / path


PO = TypeVar("PO", bound=AbstractOrchestratorParameters)
