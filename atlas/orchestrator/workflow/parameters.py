"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path

from atlas.io_utils.parameters import Parameters
from atlas.orchestrator.step import Step


class WorkflowParameters(Parameters):
    """Parameters for the workflow.
    :param name: Name of the workflow
    :type name: str
    :param dataset_path: Path of the Dataset to use in the workflow
    :type dataset_path: str
    :param steps: List of steps in the workflow.
    :type steps: list[Step]
    :param rollback_on_step_failure: If True, rollback CIS to previous step state when a step fails
    :type rollback_on_step_failure: bool
    :param create_step_snapshots: If True, create CIS snapshots before each step for debugging
    :type create_step_snapshots: bool
    :param path_from_workflow: If True, resolve relative paths from workflow file location
    :type path_from_workflow: bool
    """

    name: str | None = None
    dataset_path: Path
    steps: list[Step]
    output_dataset_path: Path
    parameters_path: Path | None = None
    path_from_workflow: bool = True
    output_dir: Path = Path()
    rollback_on_step_failure: bool = True
    create_step_snapshots: bool = False
    export_output: bool = True

    _workflow_path: Path = Path()

    @property
    def base_path(self) -> Path:
        """Returns the workflow base path if path_from_workflow is True, otherwise empty Path.

        This allows paths in parameters to be either:
        - Relative (resolved from workflow file location if path_from_workflow=True)
        - Absolute (used as-is regardless of path_from_workflow)

        :return: Base path for resolving relative paths
        :rtype: Path
        """
        return self._workflow_path if self.path_from_workflow else Path()

    def resolve_path(self, path: Path) -> Path:
        """Resolve a path based on path_from_workflow setting.

        :param path: Path to resolve (can be relative or absolute)
        :type path: Path
        :return: Resolved path (absolute paths returned as-is, relative paths resolved from base_path)
        :rtype: Path
        """
        if path.is_absolute():
            return path
        return self.base_path / path
