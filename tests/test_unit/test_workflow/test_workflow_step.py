import pytest
from unittest.mock import MagicMock
from pydantic_extra_types.pendulum_dt import DateTime
from pydantic import Field

from atlas.abstract_class.abstract_parameters import AbstractParameters
from atlas.workflow.workflow_step import WorkflowStep
from atlas.abstract_class.abstract_module import AbstractModule
from atlas.abstract_class.abstract_dataset import AbstractModuleOutput
from atlas import AtlasDataset


class DummyParams(AbstractParameters):
    param1: int = 42  # default value for testing

    # Optionally override default dates using Field
    start_date: DateTime = Field(default_factory=lambda: DateTime(year=1, month=1, day=1))
    end_date: DateTime = Field(default_factory=lambda: DateTime(year=1, month=1, day=1))
    execution_date: DateTime = Field(default_factory=lambda: DateTime(year=1, month=1, day=1))


class DummyOutput(AbstractModuleOutput):
    def build_change_sets(self) -> None:
        pass


class DummyModule(AbstractModule):
    def get_parameters_class(self):
        return DummyParams

    def import_data(self, input_data: AtlasDataset, parameters):
        return input_data

    def validate_data(self, parameters, input_dataset):
        return True

    def execute(self, parameters, input_dataset):
        output = DummyOutput()
        output.mocked = True
        return output

    def validates_results(self, parameters, input_dataset, output_dataset):
        return True

    def export_results(self, parameters, input_dataset, output_dataset):
        pass


@pytest.fixture
def input_dataset():
    return MagicMock(spec=AtlasDataset)


@pytest.fixture
def parameters():
    return {"param1": 42}


def test_workflow_step_run_stores_output(input_dataset, parameters):
    step = WorkflowStep(name="step1", module=DummyModule, parameters=parameters)

    step.run(input_dataset)

    # Output dataset is stored
    assert step.output_dataset is not None
    assert hasattr(step.output_dataset, "mocked")
    assert step.output_dataset.mocked is True

    # get_output_dataset returns the same object
    assert step.get_output_dataset() is step.output_dataset
