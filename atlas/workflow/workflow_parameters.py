"""
Copyright (c) 2016-2022, RTE (www.rte-france.com)
See AUTHORS.txt
SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import yaml


class WorkflowParameters:
    """A class containing the parameters of a workflow"""

    # Static list of all attributes:
    __slots__ = ("steps", "workflow_parameters")

    def __init__(self, parameter_file: Path):
        # Open yaml configs file
        with open(parameter_file) as f:
            data = yaml.safe_load(f)

        self.workflow_parameters = data["workflow_parameters"]
        self.steps = data["workflow_steps"]
