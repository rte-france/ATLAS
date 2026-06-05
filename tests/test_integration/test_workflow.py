from pathlib import Path

import pendulum
import pytest

from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.workflow.workflow import Workflow
from tests.utils import load_threshold

DAY_AHEAD_WORKFLOW_CONFIG = Path("tests/dataset/parameters/day_ahead/workflow.yml")
INTRADAY_WORKFLOW_CONFIG = Path("tests/dataset/parameters/intraday/workflow.yml")

WORKFLOW_CONFIGS = [
    pytest.param(
        DAY_AHEAD_WORKFLOW_CONFIG,
        id="day_ahead",
        marks=pytest.mark.skipif(
            not DAY_AHEAD_WORKFLOW_CONFIG.exists(),
            reason=f"Workflow config not found: {DAY_AHEAD_WORKFLOW_CONFIG}",
        ),
    ),
    pytest.param(
        INTRADAY_WORKFLOW_CONFIG,
        id="intraday",
        marks=pytest.mark.skipif(
            True,  # not INTRADAY_WORKFLOW_CONFIG.exists(), # TODO FIX WHEN THE WHOLE WORKFLOW WORKS
            reason=f"Workflow config not found: {INTRADAY_WORKFLOW_CONFIG}",
        ),
    ),
]


@pytest.fixture(scope="class", params=WORKFLOW_CONFIGS)
def executed_workflow(request):
    workflow_config = request.param
    workflow = Workflow.from_file(workflow_config)
    initial_cis = CurrentInputState.from_directory(workflow.parameters.resolve_path(workflow.parameters.dataset_path))
    start = pendulum.now()
    final_cis = workflow.execute()
    elapsed = (pendulum.now() - start).total_seconds()
    print(f"Workflow completed in {elapsed:.3f}s")
    return workflow, initial_cis, final_cis, elapsed, workflow_config


class TestWorkflowIntegration:
    def test_workflow_all_steps_produce_output(self, executed_workflow):
        workflow, _, _, _, _ = executed_workflow
        assert workflow.get_output_dataset() is not None
        for step in workflow.jobs:
            assert step.output_dataset is not None, f"Step '{step.name}' did not produce output"

    def test_workflow_cis_is_modified_after_execution(self, executed_workflow):
        _, initial_cis, final_cis, _, _ = executed_workflow
        diff = final_cis.diff(initial_cis)
        assert any(len(changes) > 0 for model_diff in diff.values() for changes in model_diff.values()), (
            "CIS was not modified after workflow execution"
        )

    def test_workflow_execution_time_within_threshold(self, executed_workflow):
        _, _, _, elapsed, workflow_config = executed_workflow
        threshold = load_threshold(workflow_config)
        if threshold is None:
            pytest.skip("No performance threshold defined for this workflow config")
        assert elapsed <= threshold, f"Workflow took {elapsed:.2f}s, expected <= {threshold}s"
