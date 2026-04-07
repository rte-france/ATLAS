"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from pathlib import Path

from atlas.abstract_class.abstract_orchestrator_parameters import AbstractOrchestratorParameters
from atlas.orchestrator.workflow.step import Step


class WorkflowParameters(AbstractOrchestratorParameters):
    steps: list[Step]
