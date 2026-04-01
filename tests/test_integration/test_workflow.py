from pathlib import Path

import pytest

from atlas.orchestrator.workflow.workflow import Workflow
from atlas.timing import timer

WORKFLOW_CONFIG = Path("tests/dataset/parameters/workflow.yml")


@pytest.mark.integration
@pytest.mark.skipif(
    not WORKFLOW_CONFIG.exists(),
    reason=f"Workflow config not found: {WORKFLOW_CONFIG}",
)
class TestWorkflowIntegration:
    def test_workflow_loads_without_error(self):
        workflow = Workflow.from_file(WORKFLOW_CONFIG)

        assert workflow is not None
        assert workflow.parameters.name is not None
        assert len(workflow.steps) > 0

    def test_workflow_step_names_are_unique(self):
        workflow = Workflow.from_file(WORKFLOW_CONFIG)

        step_names = [step.name for step in workflow.steps]
        assert len(step_names) == len(set(step_names)), f"Duplicate step names found: {step_names}"

    def test_workflow_all_steps_produce_output(self):
        with timer() as t:
            workflow = Workflow.from_file(WORKFLOW_CONFIG)
            workflow.execute()

            assert workflow.get_output_dataset() is not None

            for step in workflow.steps:
                assert step.output_dataset is not None, f"Step '{step.name}' did not produce output"
            print(f"Workflow completed in {t()} seconds")
