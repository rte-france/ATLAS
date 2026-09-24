"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.profiling.workflow import _patch_execute_job, _State


class _Orchestrator:
    """Minimal stand-in for AbstractOrchestrator, patched by _patch_execute_job."""

    def __init__(self, parameters):
        self.parameters = parameters

    def _execute_job(self, job, cis):  # pragma: no cover - replaced by the patch
        raise AssertionError("should have been replaced")


def _job(export_output_dataset: bool, output_dir: Path) -> MagicMock:
    job = MagicMock()
    job.name = "my_job"
    job.output_dataset = MagicMock(change_sets=[])
    job.parameters.output.export_output_dataset = export_output_dataset
    job.parameters.output.output_dir = output_dir
    return job


def _orchestrator(tmp_path: Path) -> _Orchestrator:
    parameters = MagicMock(rollback_on_job_failure=False)
    parameters.resolve_path.side_effect = lambda path: tmp_path / path
    return _Orchestrator(parameters)


class TestPatchExecuteJob:
    def test_exports_the_state_into_the_job_output_directory(self, tmp_path):
        state = _State()
        _patch_execute_job(_Orchestrator, state)

        job = _job(export_output_dataset=True, output_dir=Path("run"))
        cis = MagicMock()

        with patch("atlas.profiling.workflow.CISHandler.apply"):
            _orchestrator(tmp_path)._execute_job(job, cis)

        cis.to_directory.assert_called_once_with(tmp_path / "run" / "output_dataset")
        assert state.job_steps[0]["error"] is None

    def test_does_not_export_when_the_flag_is_off(self, tmp_path):
        state = _State()
        _patch_execute_job(_Orchestrator, state)

        job = _job(export_output_dataset=False, output_dir=Path("run"))
        cis = MagicMock()

        with patch("atlas.profiling.workflow.CISHandler.apply"):
            _orchestrator(tmp_path)._execute_job(job, cis)

        cis.to_directory.assert_not_called()

    def test_records_the_error_when_the_job_produces_nothing(self, tmp_path):
        state = _State()
        _patch_execute_job(_Orchestrator, state)

        job = _job(export_output_dataset=False, output_dir=Path("run"))
        job.output_dataset = None

        with pytest.raises(RuntimeError, match="did not produce"):
            _orchestrator(tmp_path)._execute_job(job, MagicMock())

        assert state.job_steps[0]["error"] is not None
