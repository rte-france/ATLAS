"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for Orchestrator.
"""

import heapq
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from pendulum import DateTime, Duration

from atlas import AtlasDataset
from atlas.abstract_class.job import AbstractJob
from atlas.abstract_class.orchestrator import AbstractOrchestrator
from atlas.abstract_class.orchestrator_parameters import AbstractOrchestratorParameters
from atlas.orchestrator.actionplan.action_plan import ActionPlan
from atlas.orchestrator.actionplan.job import TaskIterator
from atlas.orchestrator.workflow.workflow import Workflow


class MockJob(AbstractJob):
    def __repr__(self) -> str:
        return self.name


class MockOrchestratorParameters(AbstractOrchestratorParameters):
    pass


class MockOrchestrator(AbstractOrchestrator[MockOrchestratorParameters, MockJob]):
    def __init__(self, jobs: list[MockJob]):
        self._jobs: list[MockJob] = jobs

    @property
    def jobs(self) -> Iterator[MockJob]:
        return iter(self._jobs)

    @property
    def jobs_count(self) -> int:
        return len(self._jobs)


class MockOrchestratorFactory:
    @staticmethod
    def make_mock_output():
        mock_output = MagicMock()
        mock_output.change_sets = []
        return mock_output

    @staticmethod
    def make_mock_module(output):
        mock_instance = MagicMock()
        mock_instance.run.return_value = output
        mock_instance.get_business_model_class_used.return_value = []
        mock_instance.get_filters.return_value = None
        return MagicMock(return_value=mock_instance)

    @staticmethod
    def make_mock_job(name="step", output=None):
        mock_instance = MagicMock()
        mock_instance.run.return_value = output
        mock_instance.get_business_model_class_used.return_value = []
        mock_instance.get_filters.return_value = None
        mock_class = MagicMock(return_value=mock_instance)
        return MockJob(name, mock_class, {})

    @staticmethod
    def make_mock_parameter(tmp_path, dataset_path=None, output_path=None):
        dataset_dir = dataset_path or (tmp_path / "dataset")
        dataset_dir.mkdir(exist_ok=True)
        output_dir = output_path or (tmp_path / "output")
        output_dir.mkdir(exist_ok=True)

        config = tmp_path / "orchestrator.yaml"
        content = f"name: test_orchestrator\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\n"
        config.write_text(content)
        return MockOrchestratorParameters.from_file(config)

    @staticmethod
    def make_mock_orchestrator(tmp_path, jobs: list) -> MockOrchestrator:
        params = MockOrchestratorFactory.make_mock_parameter(tmp_path)
        orchestrator = MockOrchestrator.__new__(MockOrchestrator)
        orchestrator.parameters = params
        orchestrator._jobs = jobs
        return orchestrator

    @staticmethod
    def make_mock_action_plan(tmp_path, jobs: list) -> ActionPlan:
        class MockTaskIterator(TaskIterator):
            def __init__(self, j: MockJob, p):
                self._job: MockJob = j
                self.first_call = True
                mock_task = MagicMock()
                mock_task.from_ = DateTime.create(2000, 1, 1, 0)
                mock_task.until = DateTime.create(2000, 1, 1, 0)
                mock_task.frequency = Duration(hours=1)
                mock_task.priority = p
                super().__init__(mock_task)

            def build_jobs(self):
                return [self._job]

        params = MockOrchestratorFactory.make_mock_parameter(tmp_path)
        action_plan = ActionPlan.__new__(ActionPlan)
        action_plan.parameters = params
        priority_queue: list[TaskIterator] = []
        for priority, job in enumerate(jobs):
            heapq.heappush(priority_queue, MockTaskIterator(job, priority))
        action_plan._priority_queue = priority_queue

        return action_plan

    @staticmethod
    def make_mock_workflow(tmp_path, jobs: list) -> Workflow:
        params = MockOrchestratorFactory.make_mock_parameter(tmp_path)
        workflow = Workflow.__new__(Workflow)
        workflow.parameters = params
        workflow._jobs = jobs
        return workflow


CONCRETE_ORCHESTRATOR_BUILDERS = [
    MockOrchestratorFactory.make_mock_orchestrator,
    MockOrchestratorFactory.make_mock_action_plan,
    MockOrchestratorFactory.make_mock_workflow,
]


@pytest.fixture(params=CONCRETE_ORCHESTRATOR_BUILDERS)
def orchestrator_builder(request):
    return request.param


class TestOrchestratorExecute:
    def test_execute_runs_all_steps_in_order(self, tmp_path, orchestrator_builder):
        call_order = []
        output1 = MockOrchestratorFactory.make_mock_output()
        output2 = MockOrchestratorFactory.make_mock_output()

        def run1(ds):
            call_order.append("job1")
            job1._output_dataset = output1

        def run2(ds):
            call_order.append("job2")
            job2._output_dataset = output2

        job1 = MockOrchestratorFactory.make_mock_job("job1")
        job1.module.run = MagicMock(side_effect=lambda ds, params: output1)
        job1.run = run1

        job2 = MockOrchestratorFactory.make_mock_job("job2")
        job2.module.run = MagicMock(side_effect=lambda ds, params: output2)
        job2.run = run2

        orchestrator = orchestrator_builder(tmp_path, [job1, job2])

        with (
            patch("atlas.io_utils.atlas_dataset.AtlasDataset.from_directory", return_value=AtlasDataset()),
            patch("atlas.orchestrator.handler.cis_handler.CISHandler.apply"),
            patch("atlas.orchestrator.current_input_state.CurrentInputState") as MockCIS,
            patch.object(AtlasDataset, "to_directory"),
        ):
            mock_cis_instance = MagicMock()
            mock_cis_instance.filter_dataset.return_value = AtlasDataset()
            mock_cis_instance.data = AtlasDataset()
            MockCIS.return_value = mock_cis_instance

            orchestrator.execute()

        assert call_order == ["job1", "job2"]

    def test_execute_raises_if_step_produces_no_output(self, tmp_path, orchestrator_builder):
        job = MockOrchestratorFactory.make_mock_job("bad_step", output=None)
        # job.run will set _output_dataset = None (the default)
        orchestrator = orchestrator_builder(tmp_path, [job])

        with (
            patch("atlas.io_utils.atlas_dataset.AtlasDataset.from_directory", return_value=AtlasDataset()),
            patch("atlas.orchestrator.current_input_state.CurrentInputState") as MockCIS,
        ):
            mock_cis_instance = MagicMock()
            mock_cis_instance.filter_dataset.return_value = AtlasDataset()
            MockCIS.return_value = mock_cis_instance

            with pytest.raises(RuntimeError, match="bad_step"):
                orchestrator.execute()

    def test_execute_applies_change_sets_after_each_step(self, tmp_path, orchestrator_builder):
        mock_change_set = MagicMock()
        output = MockOrchestratorFactory.make_mock_output()
        output.change_sets = [mock_change_set]

        job = MockOrchestratorFactory.make_mock_job("job")
        job._output_dataset = output
        job.run = lambda ds: None  # run is a no-op; _output_dataset is pre-set

        orchestrator = orchestrator_builder(tmp_path, [job])

        with (
            patch("atlas.orchestrator.handler.cis_handler.CISHandler.apply") as mock_apply,
            patch("atlas.orchestrator.current_input_state.CurrentInputState.from_directory") as MockFromDir,
            patch.object(AtlasDataset, "to_directory"),
        ):
            mock_cis_instance = MagicMock()
            mock_cis_instance.filter_dataset.return_value = AtlasDataset()
            mock_cis_instance.data = AtlasDataset()
            MockFromDir.return_value = mock_cis_instance

            orchestrator.execute()

        # Default rollback_on_job_failure is True
        mock_apply.assert_called_once_with([mock_change_set], mock_cis_instance, rollback_on_error=True)

    def test_execute_save_last_step_output(self, tmp_path, orchestrator_builder):
        mock_output = MagicMock()
        job1 = MockOrchestratorFactory.make_mock_job("job1", output=MagicMock())
        job2 = MockOrchestratorFactory.make_mock_job("job2", output=mock_output)
        orchestrator = orchestrator_builder(tmp_path, [job1, job2])

        assert orchestrator.get_output_dataset() is None
        assert orchestrator.jobs_count == 2

        with (
            patch("atlas.io_utils.atlas_dataset.AtlasDataset.from_directory", return_value=AtlasDataset()),
            patch("atlas.orchestrator.handler.cis_handler.CISHandler.apply"),
            patch("atlas.orchestrator.current_input_state.CurrentInputState") as MockCIS,
            patch.object(AtlasDataset, "to_directory"),
        ):
            mock_cis_instance = MagicMock()
            mock_cis_instance.filter_dataset.return_value = AtlasDataset()
            mock_cis_instance.data = AtlasDataset()
            MockCIS.return_value = mock_cis_instance

            orchestrator.execute()

        assert orchestrator.get_output_dataset() is mock_output
