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
    """Parameters for an orchestrator
    :param name: Name of the orchestrator
    :type name: str
    :param dataset_path: Path of the Dataset to use in the workflow
    :type dataset_path: str
    """  # FIXME add missing arguments

    name: str | None = None
    dataset_path: Path
    output_dataset_path: Path
    parameters_path: Path | None = None
    path_from_orchestrator: bool = True
    output_dir: Path = Path()


PO = TypeVar("PO", bound=AbstractOrchestratorParameters)
