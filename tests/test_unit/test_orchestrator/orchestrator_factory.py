from unittest.mock import MagicMock

from pendulum import DateTime, Duration

from atlas import WorkflowJob
from atlas.abstract_class.job import AbstractJob
from atlas.orchestrator.actionplan.job import TaskIterator


class MockJob(AbstractJob):
    """Mock job class with simple representation"""

    def __repr__(self) -> str:
        return self.name


class MockTaskIterator(TaskIterator):
    def __init__(self, j: MockJob, p):
        self._job: MockJob = j
        mock_task = MagicMock()
        mock_task.from_ = DateTime.create(2000, 1, 1, 0)
        mock_task.until = DateTime.create(2000, 1, 1, 0)
        mock_task.frequency = Duration(hours=1)
        mock_task.priority = p
        super().__init__(mock_task)

    def build_jobs(self):
        return [self._job]


class MockJobFactory:
    @staticmethod
    def make_job(cls=None, name="job", output=None):
        """Make a job using the given class, name and output"""
        mock_instance = MagicMock()
        mock_instance.run.return_value = output
        mock_instance.get_business_model_class_used.return_value = []
        mock_instance.get_filters.return_value = None
        mock_class = MagicMock(return_value=mock_instance)
        if cls is None:
            return MockJobFactory.MockJob(name, mock_class, {})
        else:
            return cls(name, mock_class, {})


class MockModuleFactory:
    @staticmethod
    def make_output():
        """Return an output so no change set"""
        mock_output = MagicMock()
        mock_output.change_sets = []
        return mock_output

    @staticmethod
    def make_module_instance(output):
        """Return a module so that module.run() returns output."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = output
        mock_instance.get_business_model_class_used.return_value = []
        mock_instance.get_filters.return_value = None
        return mock_instance

    @staticmethod
    def make_module_class(output=None):
        """Return a (mock_class, mock_instance) pair where instance.run() returns output."""
        mock_instance = MockModuleFactory.make_module_instance(output)
        return MagicMock(return_value=mock_instance)

    @staticmethod
    def make_module_class_instance(output=None):
        """Return a (mock_class, mock_instance) pair where instance.run() returns output."""
        mock_instance = MockModuleFactory.make_module_instance(output)
        mock_class = MagicMock(return_value=mock_instance)
        return mock_class, mock_instance


class MockWorkflowFactory:
    @staticmethod
    def minimal_config(tmp_path, dataset_path=None, output_path=None, steps_yaml=""):
        """Write a minimal workflow YAML and return it."""
        dataset_dir = dataset_path or (tmp_path / "dataset")
        dataset_dir.mkdir(exist_ok=True)
        output_dir = output_path or (tmp_path / "output")
        output_dir.mkdir(exist_ok=True)

        config = tmp_path / "workflow.yaml"
        content = f"name: test_workflow\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\nsteps: []\n"
        if steps_yaml:
            content = (
                f"name: test_workflow\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\n{steps_yaml}"
            )
        config.write_text(content)
        return config

    @staticmethod
    def make_job(name="job", output=None):
        """Return a WorkflowJob with a mock module that returns *output*."""
        mock_instance = MagicMock()
        mock_instance.run.return_value = output
        mock_instance.get_business_model_class_used.return_value = []
        mock_instance.get_filters.return_value = None

        mock_class = MagicMock(return_value=mock_instance)
        return WorkflowJob(name, mock_class, {})


class MockOrchestratorFactory:
    @staticmethod
    def make_mock_job(name="step", output=None):
        mock_instance = MagicMock()
        mock_instance.run.return_value = output
        mock_instance.get_business_model_class_used.return_value = []
        mock_instance.get_filters.return_value = None
        mock_class = MagicMock(return_value=mock_instance)
        return MockJob(name, mock_class, {})

    @staticmethod
    def minimal_config(tmp_path, dataset_path=None, output_path=None):
        """Write a minimal YAML for any orchestrator and return it."""
        dataset_dir = dataset_path or (tmp_path / "dataset")
        dataset_dir.mkdir(exist_ok=True)
        output_dir = output_path or (tmp_path / "output")
        output_dir.mkdir(exist_ok=True)

        config = tmp_path / "orchestrator.yaml"
        content = f"name: test_orchestrator\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\n"
        config.write_text(content)
        return config


class MockActionPlanFactory:
    @staticmethod
    def minimal_config(tmp_path, dataset_path=None, output_path=None, tasks_yaml=""):
        """Write a minimal YAML for any orchestrator and return it."""
        dataset_dir = dataset_path or (tmp_path / "dataset")
        dataset_dir.mkdir(exist_ok=True)
        output_dir = output_path or (tmp_path / "output")
        output_dir.mkdir(exist_ok=True)

        config = tmp_path / "action_plan.yaml"
        content = f"name: test_workflow\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\ntasks: []\n"
        if tasks_yaml:
            content = (
                f"name: test_workflow\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\n{tasks_yaml}"
            )
        config.write_text(content)
        return config
