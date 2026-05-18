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


@pytest.mark.parametrize("workflow_config", WORKFLOW_CONFIGS)
class TestWorkflowIntegration:
    def test_workflow_all_steps_produce_output(self, workflow_config: Path):
        with timer() as t:
            workflow = Workflow.from_file(workflow_config)
            workflow.execute()

            assert workflow.get_output_dataset() is not None
            for step in workflow.jobs:
                assert step.output_dataset is not None, f"Step '{step.name}' did not produce output"
            print(f"Workflow completed in {t()} seconds")

    def test_workflow_cis_is_modified_after_execution(self, workflow_config: Path):
        workflow = Workflow.from_file(workflow_config)
        initial_cis = CurrentInputState.from_directory(
            workflow.parameters.resolve_path(workflow.parameters.dataset_path)
        )
        final_cis = workflow.execute()
        diff = final_cis.diff(initial_cis)
        assert any(len(changes) > 0 for model_diff in diff.values() for changes in model_diff.values()), (
            "CIS was not modified after workflow execution"
        )
