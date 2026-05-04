from collections.abc import Iterator
from unittest.mock import MagicMock

import yaml
from pendulum import Duration

from atlas.abstract_class.job import AbstractJob
from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.abstract_class.orchestrator_parameters import AbstractOrchestratorParameters
from atlas.io_utils.parameters import ContextParameters
from atlas.orchestrator.actionplan.job import Task, TaskIterator


class ConcreteJob(AbstractJob):
    """Minimalist implementation of AbstractJob"""

    def __repr__(self) -> str:
        return self.name


class ConcreteTaskIterator(TaskIterator):
    """Minimalist implementation of TaskIterator"""

    def __init__(self, task: Task, job: ConcreteJob):
        self._job: ConcreteJob = job
        super().__init__(task)

    def build_jobs(self):
        return [self._job]


class ConcreteOrchestratorParameters(AbstractOrchestratorParameters):
    """Minimalist implementation of AbstractOrchestratorParameters"""

    pass


class ConcreteOrchestrator(AbstractOrchestrator[ConcreteOrchestratorParameters, ConcreteJob]):
    """Minimalist implementation of AbstractOrchestrator"""

    def __init__(self, jobs: list[ConcreteJob]):
        self._jobs: list[ConcreteJob] = jobs

    @property
    def jobs(self) -> Iterator[ConcreteJob]:
        return iter(self._jobs)

    @property
    def jobs_count(self) -> int:
        return len(self._jobs)


class MockOutPutBuilder:
    """Default: an output with no change set"""

    def __init__(self):
        self.mock_output = MagicMock()
        self.mock_output.change_sets = []

    def build(self):
        return self.mock_output


class MockModuleBuilder:
    """Default: return a module so that module.run() returns an output with no change set."""

    def __init__(self):
        self.instance = MagicMock()
        self.instance.run.return_value = MockOutPutBuilder.build()
        self.instance.get_business_model_class_used.return_value = []
        self.instance.get_filters.return_value = None

    def with_output(self, output) -> MockModuleBuilder:
        self.instance.run.return_value = output
        return self

    def build(self):
        return self.instance


class MockJobBuilder:
    """Default: a job named "job" with a None output, no parameter and a minimalist implementation of AbstractJob"""

    def __init__(self):
        self.name = "job"
        self.output = None
        self.module_parameters = {}
        self.cls = ConcreteJob.__class__
        self.module = None

    def with_name(self, name) -> MockJobBuilder:
        self.name = name
        return self

    def with_output(self, output) -> MockJobBuilder:
        self.output = output
        return self

    def with_class(self, cls) -> MockJobBuilder:
        self.cls = cls
        return self

    def with_module_parameters(self, parameters) -> MockJobBuilder:
        self.module_parameters = parameters
        return self

    def with_module(self, module) -> MockJobBuilder:
        self.module = module
        self.cls = module.__class__
        return self

    def build(self):
        if self.module is None:
            module_builder = MockModuleBuilder.with_output(self.output)
            self.module = module_builder.build()
            self.cls = MagicMock(return_value=self.module)
        return self.cls(self.name, self.cls, self.module_parameters)


class OrchestratorConfigBuilder:
    """Default: a path to a minimal orchestrator YAML with no job named test_orchestrator."""

    def __init__(self):
        self.name = "test_orchestrator"
        self.dataset_dir = None
        self.output_dir = None
        self.context = ""
        self.misc = ""

    def with_name(self, name) -> OrchestratorConfigBuilder:
        self.name = name
        return self

    def with_dataset_dir(self, dataset_dir) -> OrchestratorConfigBuilder:
        self.dataset_dir = dataset_dir
        return self

    def with_output_dir(self, output_dir) -> OrchestratorConfigBuilder:
        self.output_dir = output_dir
        return self

    def with_context(self, context) -> OrchestratorConfigBuilder:
        if context is str:
            self.context = context
        elif context is ContextParameters:
            self.context = yaml.dump(context)
        else:
            raise TypeError(f"context must be str or ContextParameters, not {type(context)}")
        return self

    def with_any(self, misc) -> OrchestratorConfigBuilder:
        self.misc = misc
        return self

    def build(self, tmp_path):
        if self.dataset_dir is None:
            self.dataset_dir = tmp_path / "dataset"
        if self.output_dir is None:
            self.output_dir = tmp_path / "output"

        self.dataset_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        config = tmp_path / "orchestrator_config.yaml"
        content = (
            f"name: {self.name}\n"
            f"dataset_path: {self.dataset_dir}\n"
            f"output_dataset_path: {self.output_dir}\n"
            f"{self.context}\n"
            f"{self.misc}\n"
        )
        config.write_text(content)
        return config


class MockTaskBuilder:
    def __init__(self):
        self.mock_instance = MagicMock()
        self.mock_instance.offset_start_date = Duration(hours=1)
        self.mock_instance.offset_end_date = Duration(hours=1)
        self.mock_instance.priority = 1

    def with_from(self, from_) -> MockTaskBuilder:
        self.mock_instance = from_
        return self

    def with_until(self, until) -> MockTaskBuilder:
        self.mock_instance = until
        return self

    def with_frequency(self, frequency) -> MockTaskBuilder:
        self.mock_instance = frequency
        return self

    def with_offset_start_date(self, offset_start_date) -> MockTaskBuilder:
        self.mock_instance.offset_start_date = offset_start_date
        return self

    def with_offset_end_date(self, offset_end_date) -> MockTaskBuilder:
        self.mock_instance.offset_end_date = offset_end_date
        return self

    def with_priority(self, priority: int) -> MockTaskBuilder:
        self.mock_instance.priority = priority
        return self

    def build(self) -> Task:
        return self.mock_instance
