from pathlib import Path
from typing import Any

import pytest
import yaml

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import (
    AbstractDataset,
    input_dataset_type_var,
    output_dataset_type_var,
)
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.abstract_class.abstract_parameters import AbstractParameters, module_parameters_type_var
from atlas.workflow.workflow import Workflow
from atlas.workflow.workflow_helper import WorkflowHelper
from atlas.workflow.workflow_parameters_parser import WorkflowParametersParser
from atlas.workflow.workflow_step import WorkflowStep


@pytest.fixture
def workflow_yaml_file(tmp_path: Path) -> Path:
    # Define the YAML content as a dictionary
    yaml_dict = {
        "parameters": {"dataset_path": "dataset/path"},
        "steps": {
            "step1": {"name": "test1", "parameters_path": "module_parameters/path"},
            "step2": {"name": "test2", "parameters_path": "module_parameters/path"},
        },
    }

    # Dump dictionary to YAML file
    yaml_path = tmp_path / "workflow_parameters.yml"
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_dict, f)

    return yaml_path


class ModuleTest(AbstractModule):
    def execute(
        self, parameters: module_parameters_type_var, input_dataset: input_dataset_type_var
    ) -> output_dataset_type_var:
        output_dataset = input_dataset
        output_dataset.data += 1
        return output_dataset

    def get_parameters_class(self) -> type[module_parameters_type_var]:
        return AbstractParameters

    def import_data(
        self, raw_data: dict[str, list[BusinessModel]], parameters: module_parameters_type_var
    ) -> input_dataset_type_var:
        pass

    def validate_data(self, parameters: module_parameters_type_var, input_dataset: input_dataset_type_var) -> bool:
        pass

    def validates_results(
        self,
        parameters: module_parameters_type_var,
        input_dataset: input_dataset_type_var,
        output_dataset: output_dataset_type_var,
    ) -> bool:
        pass

    def export_results(
        self,
        parameters: module_parameters_type_var,
        input_dataset: input_dataset_type_var,
        output_dataset: output_dataset_type_var,
    ) -> None:
        pass


class ModuleParamsTest(AbstractParameters):
    def __init__(self, filepath):
        pass


class DatasetTest(AbstractDataset):
    def __init__(self, filepath):
        self.data = 0

    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []


def test_parameters_reading(workflow_yaml_file: Path):
    wfp = WorkflowParametersParser().from_file(workflow_yaml_file)
    assert wfp.parameters.dataset_path == "dataset/path"
    assert wfp.steps["step1"].name == "test1"
    assert wfp.steps["step2"].name == "test2"


def test_basic_workflow(workflow_yaml_file: Path):
    wfp = WorkflowParametersParser().from_file(workflow_yaml_file)
    datasetTest = DatasetTest(None)
    module_params = ModuleParamsTest(wfp.steps["step1"].parameters_path)
    wf = WorkflowHelper.create_simple_workflow(datasetTest, module_params, ModuleTest())
    wf.execute()
    assert wf.get_output_dataset() is not None


def test_workflow(workflow_yaml_file: Path):
    wfp = WorkflowParametersParser().from_file(workflow_yaml_file)
    datasetTest = DatasetTest(None)
    params_step1 = ModuleParamsTest(wfp.steps["step1"].parameters_path)
    params_step2 = ModuleParamsTest(wfp.steps["step2"].parameters_path)

    wf = Workflow("wf_test", datasetTest, None)
    wf.add_step(WorkflowStep("step1", params_step1, ModuleTest()))
    wf.add_step(WorkflowStep("step2", params_step2, ModuleTest()))
    assert len(wf.steps) == 2
    wf.execute()
    assert wf.get_output_dataset().data == 2
