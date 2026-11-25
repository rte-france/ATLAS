"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

`TaskRef` / `StepRef`: position of each job in the orchestrator that generates it.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from atlas.orchestrator.job_reference import StepRef, TaskRef


def test_task_and_step_refs_are_immutable():
    with pytest.raises(FrozenInstanceError):
        TaskRef("day_ahead", 1).iteration = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        StepRef("clearing", is_first=True, is_last=True).is_last = False  # type: ignore[misc]
