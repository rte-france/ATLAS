import pytest
from pathlib import Path
from atlas.workflow.workflow_parameters_parser import WorkflowParametersParser, WorkflowParameters, Step


def test_parse_yaml_returns_dict(tmp_path):
    yaml_file = tmp_path / "params.yaml"
    yaml_file.write_text("""
    name: my_workflow
    dataset_path: /tmp/input
    output_dataset_path: /tmp/output
    steps:
      step1:
        name: dummy_step
        parameters_path: /tmp/step1.yaml
    """)

    parsed = WorkflowParametersParser._parse_yaml(yaml_file)
    assert isinstance(parsed, dict)
    assert parsed["name"] == "my_workflow"
    assert "steps" in parsed


def test_from_file_returns_workflow_parameters(tmp_path):
    yaml_file = tmp_path / "workflow.yaml"
    yaml_file.write_text("""
    name: my_workflow
    dataset_path: /tmp/input
    output_dataset_path: /tmp/output
    steps:
      step1:
        name: dummy_step
        parameters_path: /tmp/step1.yaml
    """)

    wf_params = WorkflowParametersParser.from_file(yaml_file)
    assert isinstance(wf_params, WorkflowParameters)
    assert wf_params.name == "my_workflow"
    assert "step1" in wf_params.steps
    step = wf_params.steps["step1"]
    assert isinstance(step, Step)
    assert step.name == "dummy_step"
    assert Path(step.parameters_path) == Path("/tmp/step1.yaml")


def test_from_file_unsupported_extension(tmp_path):
    file = tmp_path / "workflow.txt"
    file.write_text("dummy content")
    with pytest.raises(ValueError, match="Unsupported file extension"):
        WorkflowParametersParser.from_file(file)
