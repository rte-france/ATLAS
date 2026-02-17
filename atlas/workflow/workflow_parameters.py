"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

from pydantic import BaseModel

from atlas.io_utils.parameters import Parameters


class Step(BaseModel):
    """Definition of a single step in the workflow.

    :param name: Unique name identifying the step.
    :type name: str
    :param parameters_path: Path to the parameters file for the step.
    :type parameters_path: str
    """

    name: str
    parameters_path: Path


class WorkflowParameters(Parameters):
    """Parameters for the workflow.
    :param name: Name of the workflow
    :type name: str
    :param dataset_path: Path of the Dataset to use in the workflow
    :type dataset_path: str
    :param steps: List of steps in the workflow.
    :type steps: list[Step]
    """

    dataset_path: Path
    steps: list[Step]
    output_dataset_path: Path
    name: str | None = None
    generic_module_parameters_path: Path | None = None
