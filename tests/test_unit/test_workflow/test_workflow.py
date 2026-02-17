import pytest
from unittest.mock import patch, MagicMock

from atlas.workflow.workflow import Workflow, WorkflowStep
from atlas.workflow.workflow_parameters_parser import WorkflowParameters, Step


class DummyModule:
    def __init__(self, parameters):
        self.parameters = parameters
        self.output_dataset = MagicMock()


# ==========================================================
# Fixtures
# ==========================================================
@pytest.fixture
def tmp_paths(tmp_path):
    input_path = tmp_path / "input"
    output_path = tmp_path / "output"
    input_path.mkdir()
    return input_path, output_path


@pytest.fixture
def step_file(tmp_path):
    file = tmp_path / "params.yaml"
    file.write_text("{}")
    return file


@pytest.fixture
def workflow_parameters(tmp_paths, step_file):
    input_path, output_path = tmp_paths
    return WorkflowParameters(
        name="test_workflow",
        dataset_path=input_path,
        output_dataset_path=output_path,
        generic_module_parameters_path=None,
        steps={
            "step1": Step(name="dummy", parameters_path=step_file),
        },
    )


def test_build_generic_module_parameters_loads_values(tmp_path, workflow_parameters):
    yaml_file = tmp_path / "generic.yaml"
    yaml_file.write_text("param1: 42\nparam2: 'test'")
    workflow_parameters.generic_module_parameters_path = yaml_file

    wf = Workflow(workflow_parameters)
    wf.build_generic_module_parameters()

    assert wf.generic_module_parameters["param1"] == 42
    assert wf.generic_module_parameters["param2"] == "test"


def test_build_generic_module_parameters_no_path(workflow_parameters):
    wf = Workflow(workflow_parameters)
    wf.build_generic_module_parameters()
    assert wf.generic_module_parameters == {}


@patch("atlas.workflow.workflow.WorkflowHelper")
def test_build_step_unknown_module_raises(mock_helper, workflow_parameters, step_file):
    mock_helper.MODULE_REGISTRY = {}

    wf = Workflow(workflow_parameters)
    with pytest.raises(ValueError):
        wf.build_step("step1", workflow_parameters.steps["step1"])


@patch("atlas.workflow.workflow.WorkflowHelper")
def test_build_step_creates_workflowstep(mock_helper, workflow_parameters, step_file):
    mock_helper.MODULE_REGISTRY = {"dummy": DummyModule}

    wf = Workflow(workflow_parameters)
    wf.build_step("step1", workflow_parameters.steps["step1"])

    assert len(wf.steps) == 1
    step = wf.steps[0]
    assert isinstance(step, WorkflowStep)
    assert step.name == "step1"
    assert isinstance(step.module, DummyModule)
    assert isinstance(step.parameters, dict)


@patch("atlas.workflow.workflow.WorkflowHelper")
def test_get_output_dataset_returns_last_step_output(mock_helper, workflow_parameters):
    mock_helper.MODULE_REGISTRY = {"dummy": DummyModule}

    wf = Workflow(workflow_parameters)
    wf.build_step("step1", workflow_parameters.steps["step1"])

    last_dataset = MagicMock()
    wf.steps[0].output_dataset = last_dataset

    assert wf.get_output_dataset() == last_dataset


@patch("atlas.workflow.workflow.WorkflowHelper")
def test_build_steps_merges_generic_and_custom(mock_helper, tmp_path, workflow_parameters):
    step_file = workflow_parameters.steps["step1"].parameters_path
    step_file.write_text("custom: 123")

    # Generic params
    generic_file = tmp_path / "generic.yaml"
    generic_file.write_text("common: 1")
    workflow_parameters.generic_module_parameters_path = generic_file

    mock_helper.MODULE_REGISTRY = {"dummy": DummyModule}

    wf = Workflow(workflow_parameters)
    wf.build_generic_module_parameters()
    wf.build_steps()

    step = wf.steps[0]
    assert step.parameters["common"] == 1
    assert step.parameters["custom"] == 123
