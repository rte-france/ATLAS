from pathlib import Path

from atlas.workflow.workflow_parameters import WorkflowParameters


def test_parameters_reading():
    wfp = WorkflowParameters(Path("workflow_parameters.yml"))
    assert wfp.workflow_parameters["dataset_path"] == "some/path"
    assert wfp.steps["step1"] == "test1"
    assert wfp.steps["step2"] == "test2"
