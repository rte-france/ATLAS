from pathlib import Path
from typing import Any

from atlas import BusinessModel
from atlas.abstract_class.abstract_dataset import input_dataset_type_var, output_dataset_type_var, AbstractDataset
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.abstract_class.abstract_parameters import module_parameters_type_var, AbstractParameters
from atlas.workflow.workflow_helper import WorkflowHelper
from atlas.workflow.workflow_parameters import WorkflowParameters


class ModuleTest(AbstractModule):
    def execute(
        self, parameters: module_parameters_type_var, input_dataset: input_dataset_type_var
    ) -> output_dataset_type_var:
        return DatasetTest()

    def create_parameters(self, raw_params: dict[str, Any]) -> module_parameters_type_var:
        """Creates a concrete parameters object from raw dictionary."""
        pass

    def import_data(
        self, raw_data: dict[str, list[BusinessModel]], parameters: module_parameters_type_var
    ) -> input_dataset_type_var:
        """Imports data using business objects and parameters."""
        pass

    def validate_data(self, parameters: module_parameters_type_var, input_dataset: input_dataset_type_var) -> bool:
        """Validates imported or generated data."""
        pass

    def validates_results(
        self,
        parameters: module_parameters_type_var,
        input_dataset: input_dataset_type_var,
        output_dataset: output_dataset_type_var,
    ) -> bool:
        """Validates results"""
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
    def get_business_model_class_used(self) -> list[type[BusinessModel]]:
        return []


def test_parameters_reading():
    wfp = WorkflowParameters(Path("workflow_parameters.yml"))
    assert wfp.workflow_parameters["dataset_path"] == "dataset/path"
    assert wfp.steps["step1"]["name"] == "test1"
    assert wfp.steps["step2"]["name"] == "test2"


def test_basic_workflow():
    wfp = WorkflowParameters(Path("workflow_parameters.yml"))
    datasetTest = DatasetTest()
    module_params = ModuleParamsTest(wfp.steps["step1"]["parameters"])
    wf = WorkflowHelper.create_simple_workflow(datasetTest, module_params, ModuleTest())
    wf.execute()
    assert wf.get_output_dataset() is not None
