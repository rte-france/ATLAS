from collections.abc import Iterator
from typing import Self
from unittest.mock import MagicMock

import yaml
from pendulum import Duration, DateTime

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
        super().__init__(task)
        self._job: ConcreteJob = job

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

class MockModuleParametersBuilder:
    def __init__(self):
        self.temporal = MagicMock()
        self.temporal.start_date = None
        self.temporal.end_date = None
        self.temporal.execution_date = None
        self.temporal.timestep = Duration(minutes=60)
        self.output = None
        self.relative_src = None

    def with_start_date(self, date) -> Self:
        self.temporal.start_date = date
        return self

    def with_end_date(self, date) -> Self:
        self.temporal.end_date = date
        return self

    def with_execution_date(self, date) -> Self:
        self.temporal.execution_date = date
        return self

    def with_timestep_date(self, duration) -> Self:
        self.temporal.timestep = duration
        return self

    def with_output(self, path) -> Self:
        self.output = path
        return self

    def with_relative_src(self, path) -> Self:
        self.relative_src = path
        return self

    def build(self, tmp_path = None):
        if not self.output and tmp_path is not None:
            self.output = tmp_path / "output_path"
        if not self.relative_src and tmp_path is not None:
            self.relative_src = tmp_path / "relative_src"
        return self

class MockModuleBuilder:
    """Default: return a module so that module.run() returns an output with no change set."""

    def __init__(self):
        self.instance = MagicMock()
        self.instance.run.return_value = MockOutPutBuilder().build()
        self.instance.get_business_model_class_used.return_value = []
        self.instance.get_filters.return_value = None

    def with_output(self, output) -> Self:
        self.instance.run.return_value = output
        return self

    def build(self):
        return self.instance


class MockJobBuilder:
    """Default: a job named "job" with a None output, no parameter and a minimalist implementation of AbstractJob"""

    def __init__(self):
        self.name = "job"
        self.output = MockOutPutBuilder().build()
        self.module_parameters = {}
        self.job_cls = ConcreteJob
        self.module_cls = None
        self.module = None

    def with_name(self, name) -> Self:
        self.name = name
        return self

    def with_output(self, output) -> Self:
        self.output = output
        return self

    def with_job_class(self, cls) -> Self:
        self.job_cls = cls
        return self

    def with_module_parameters(self, parameters) -> Self:
        self.module_parameters = parameters
        return self

    def with_module(self, module) -> Self:
        self.module = module
        self.module_cls = module.__class__
        return self

    def build(self):
        if self.module is None:
            self.module = MockModuleBuilder().with_output(self.output).build()
            self.module_cls = MagicMock(return_value=self.module)
        return self.job_cls(self.name, self.module_cls, self.module_parameters)


class OrchestratorConfigBuilder:
    """Default: a path to a minimal orchestrator YAML with no job named test_orchestrator."""

    def __init__(self):
        self.name = "test_orchestrator"
        self.dataset_dir = None
        self.output_dir = None
        self.context = ""
        self.misc = ""

    def with_name(self, name) -> Self:
        self.name = name
        return self

    def with_dataset_dir(self, dataset_dir) -> Self:
        self.dataset_dir = dataset_dir
        return self

    def with_output_dir(self, output_dir) -> Self:
        self.output_dir = output_dir
        return self

    def with_context(self, context) -> Self:
        if type(context) is str:
            self.context = context
        elif type(context) is ContextParameters:
            self.context = yaml.dump(context)
        else:
            raise TypeError(f"context must be str or ContextParameters, not {type(context)}")
        return self

    def with_any(self, misc) -> Self:
        self.misc = misc
        return self

    def build_workflow(self, tmp_path):
        if self.misc == "":
            self.misc = "steps: []"
        return self.build(tmp_path)

    def build_action_plan(self, tmp_path):
        if self.misc == "":
            self.misc = "tasks: []"
        return self.build(tmp_path)

    def build(self, tmp_path):
        if self.dataset_dir is None:
            self.dataset_dir = tmp_path / "dataset"

        self.dataset_dir.mkdir(exist_ok=True)
        config = tmp_path / "orchestrator_config.yaml"

        if self.output_dir is not None:
            self.output_dir.mkdir(exist_ok=True)
            content = (
                f"name: {self.name}\n"
                f"dataset_path: {self.dataset_dir}\n"
                f"output_dataset_path: {self.output_dir}\n"
                f"{self.context}\n"
                f"{self.misc}\n"
            )
        else: #FIXME improve code
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
        self.from_ = DateTime(2026, 1, 1)
        self.until = DateTime(2026, 1, 1)
        self.frequency = Duration(days=1)
        self.offset_start_date = Duration(days=1)
        self.offset_end_date = Duration(days=2)
        self.priority = 1
        self.module = None
        self.workflow = None
        self.parameters = None

    def with_from_until_frequency(self, from_, until, frequency) -> Self:
        self.from_ = from_
        self.until = until
        self.frequency = frequency
        return self

    def with_offset_start_date(self, offset_start_date) -> Self:
        self.offset_start_date = offset_start_date
        return self

    def with_offset_end_date(self, offset_end_date) -> Self:
        self.offset_end_date = offset_end_date
        return self

    def with_priority(self, priority: int) -> Self:
        self.priority = priority
        return self

    def with_module(self, module) -> Self:
        self.module = module
        return self

    def with_workflow(self, workflow) -> Self:
        self.workflow = workflow
        return self

    def with_parameters(self, parameters) -> Self:
        self.parameters = parameters
        return self

    def build(self):
        return self
