"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path

from atlas.io_utils.parameters import Parameters
from atlas.workflow.step import Step


class WorkflowParameters(Parameters):
    """Parameters for the workflow.
    :param name: Name of the workflow
    :type name: str
    :param dataset_path: Path of the Dataset to use in the workflow
    :type dataset_path: str
    :param steps: List of steps in the workflow.
    :type steps: list[Step]
    """

    name: str | None = None
    dataset_path: Path
    steps: list[Step]
    output_dataset_path: Path
    parameters_path: Path | None = None
    path_from_workflow: bool = True
    export_output: bool = True
    output_dir: Path = Path()
