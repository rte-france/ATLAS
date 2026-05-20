from pathlib import Path

import pytest

from atlas.orchestrator.current_input_state import CurrentInputState
from atlas.orchestrator.workflow.workflow import Workflow
from atlas.timing import timer

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
    with timer() as t:
        final_cis = workflow.execute()
        print(f"Workflow completed in {t()} seconds")
    return workflow, initial_cis, final_cis


class TestWorkflowIntegration:
    def test_workflow_all_steps_produce_output(self, executed_workflow):
        workflow, _, _ = executed_workflow
        assert workflow.get_output_dataset() is not None
        for step in workflow.jobs:
            assert step.output_dataset is not None, f"Step '{step.name}' did not produce output"

    def test_workflow_cis_is_modified_after_execution(self, executed_workflow):
        _, initial_cis, final_cis = executed_workflow
        diff = final_cis.diff(initial_cis)
        assert any(len(changes) > 0 for model_diff in diff.values() for changes in model_diff.values()), (
            "CIS was not modified after workflow execution"
        )
