from unittest.mock import MagicMock

import pytest

from atlas import AtlasDataset
from atlas.core.orchestrator.actionplan.job import ActionPlanJob
from atlas.core.orchestrator.workflow.job import WorkflowJob
from tests.test_unit.test_orchestrator.orchestrator_factory import ConcreteJob, MockModuleBuilder

CONCRETE_JOB_BUILDERS = [
    ConcreteJob,
    ActionPlanJob,
    WorkflowJob,
]


@pytest.fixture(params=CONCRETE_JOB_BUILDERS)
def job_builder(request):
    return request.param


class TestJobInit:
    @pytest.fixture(autouse=True)
    def set_up_mock_module(self):
        self.mock_instance = MockModuleBuilder().build()
        self.mock_class = MagicMock(return_value=self.mock_instance)

    def test_init_sets_name(self, job_builder):
        job = job_builder("my_job", self.mock_class, {})
        assert job.name == "my_job"

    def test_init_instantiates_module(self, job_builder):
        job = job_builder("my_job", self.mock_class, {})
        self.mock_class.assert_called_once()
        assert job.module is self.mock_instance

    def test_output_dataset_is_none_before_run(self, job_builder):
        job = job_builder("my_job", self.mock_class, {})
        assert job.output_dataset is None
        assert job.get_output_dataset() is None


class TestJobRun:
    @pytest.fixture
    def atlas_dataset(self):
        return AtlasDataset()

    @pytest.fixture(autouse=True)
    def set_up_module_and_job(self, job_builder):
        mock_output = MagicMock()
        self.mock_instance = MockModuleBuilder().with_output(mock_output).build()
        self.mock_class = MagicMock(return_value=self.mock_instance)
        self.mock_output = mock_output
        self.job = job_builder("job", self.mock_class, {})

    def test_run_calls_module_run(self, atlas_dataset, job_builder):
        job = job_builder("job", self.mock_class, {"param": 1})
        job.run(atlas_dataset)
        self.mock_instance.run.assert_called_once_with(atlas_dataset, job.parameters)

    def test_run_stores_output_dataset(self, atlas_dataset):
        self.job.run(atlas_dataset)
        assert self.job.output_dataset is self.mock_output
        assert self.job.get_output_dataset() is self.mock_output

    def test_run_with_none_output_stores_none(self, atlas_dataset, job_builder):
        mock_instance = MockModuleBuilder().with_output(None).build()
        mock_class = MagicMock(return_value=mock_instance)
        job = job_builder("job", mock_class, {})
        job.run(atlas_dataset)
        assert job.output_dataset is None

    def test_run_overwrites_previous_output(self, atlas_dataset, job_builder):
        first_output = MagicMock(name="first")
        second_output = MagicMock(name="second")
        self.mock_instance.run.side_effect = [first_output, second_output]

        job = job_builder("job", self.mock_class, {})
        job.run(atlas_dataset)
        assert job.output_dataset is first_output

        job.run(atlas_dataset)
        assert job.output_dataset is second_output

    def test_run_propagates_module_exception(self, atlas_dataset, job_builder):
        self.mock_instance.run.side_effect = RuntimeError("module crashed")

        job = job_builder("job", self.mock_class, {})
        with pytest.raises(RuntimeError, match="module crashed"):
            job.run(atlas_dataset)

    def test_output_dataset_property_and_get_method_are_consistent(self, atlas_dataset, job_builder):
        job = job_builder("job", self.mock_class, {})
        job.run(atlas_dataset)

        assert job.output_dataset is job.get_output_dataset()
