"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

`TaskRef` / `StepRef`: position of each job in the orchestrator that generates it.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from atlas.orchestrator.job_reference import StepRef, TaskRef
from atlas.orchestrator.workflow.workflow import Workflow

# a standalone workflow receives no dates from an action plan: its steps need complete parameters
MODULE_PARAMETERS_WITH_DATES = {
    "temporal": {
        "start_date": "2028-01-01 00:00:00",
        "end_date": "2028-01-02 00:00:00",
        "execution_date": "2027-12-31 12:00:00",
        "timestep": "PT1H",
    }
}


def _write_yaml(path: Path, content: dict) -> Path:
    path.write_text(yaml.safe_dump(content))
    return path


def _workflow_config(tmp_path: Path, module_parameters: dict) -> dict:
    (tmp_path / "dataset").mkdir(exist_ok=True)
    parameters_file = _write_yaml(tmp_path / "module_parameters.yml", module_parameters)
    return {
        "dataset_path": str(tmp_path / "dataset"),
        "steps": [
            {"name": "first", "module": "MarketClearing", "parameters": str(parameters_file)},
            {"name": "second", "module": "MarketClearing", "parameters": str(parameters_file)},
        ],
    }


def test_task_and_step_refs_are_immutable():
    with pytest.raises(FrozenInstanceError):
        TaskRef("day_ahead", 1).iteration = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        StepRef("clearing", is_first=True, is_last=True).is_last = False  # type: ignore[misc]


def test_standalone_workflow_jobs_have_a_step_but_no_task(tmp_path: Path):
    workflow_file = _write_yaml(tmp_path / "workflow.yml", _workflow_config(tmp_path, MODULE_PARAMETERS_WITH_DATES))
    workflow = Workflow.from_file(workflow_file)

    assert [(job.task, job.step) for job in workflow.jobs] == [
        (None, StepRef("first", is_first=True, is_last=False)),
        (None, StepRef("second", is_first=False, is_last=True)),
    ]
