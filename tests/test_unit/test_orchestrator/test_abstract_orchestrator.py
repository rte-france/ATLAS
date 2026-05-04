"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for Orchestrator.
"""

import heapq
from unittest.mock import MagicMock, patch

import pytest

from atlas import AtlasDataset, WorkflowParameters
from atlas.io_utils.parameters import ContextParameters
from atlas.orchestrator.actionplan.action_plan import ActionPlan
from atlas.orchestrator.actionplan.job import TaskIterator
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters
from atlas.orchestrator.workflow.workflow import Workflow
from tests.test_unit.test_orchestrator.orchestrator_factory import (
    ConcreteTaskIterator,
    MockActionPlanFactory,
    MockModuleFactory,
    MockOrchestratorFactory,
    MockWorkflowFactory,
)


@staticmethod
def make_mock_orchestrator(
    tmp_path, jobs: list, yaml_context: str = "", overall_context: ContextParameters | None = None
) -> MockOrchestrator:
    config = MockOrchestratorFactory.minimal_config(tmp_path, context=yaml_context)
    params = MockOrchestratorParameters.from_file(config)
    orchestrator = MockOrchestrator.__new__(MockOrchestrator)
    orchestrator.parameters = params
    orchestrator.parameters.context.use(overall_context)
    orchestrator._jobs = jobs
    return orchestrator


@staticmethod
def make_mock_workflow(
    tmp_path, jobs: list, yaml_context: str = "", overall_context: ContextParameters | None = None
) -> Workflow:
    config = MockWorkflowFactory.minimal_config(tmp_path, context=yaml_context)
    params = WorkflowParameters.from_file(config, overall_context)
    workflow = Workflow.__new__(Workflow)
    workflow.parameters = params
    workflow._jobs = jobs
    return workflow


@staticmethod
def make_mock_action_plan(
    tmp_path, jobs: list, yaml_context: str = "", overall_context: ContextParameters | None = None
) -> ActionPlan:
    config = MockActionPlanFactory.minimal_config(tmp_path, context=yaml_context)
    params = ActionPlanParameters.from_file(config, overall_context)
    action_plan = ActionPlan.__new__(ActionPlan)
    action_plan.parameters = params
    priority_queue: list[TaskIterator] = []
    for priority, job in enumerate(jobs):
        heapq.heappush(priority_queue, ConcreteTaskIterator(job, priority))
    action_plan._priority_queue = priority_queue
    action_plan._jobs_count = len(jobs)
    return action_plan


CONCRETE_ORCHESTRATOR_BUILDERS = [
    make_mock_orchestrator,
    make_mock_action_plan,
    make_mock_workflow,
]


@pytest.fixture(params=CONCRETE_ORCHESTRATOR_BUILDERS)
def orchestrator_builder(request):
    return request.param


class TestOrchestratorExecute:
    def test_execute_runs_all_steps_in_order(self, tmp_path, orchestrator_builder):
        call_order = []
        output1 = MockModuleFactory.make_output()
        output2 = MockModuleFactory.make_output()

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

        assert call_order == ["job1", "job2"]

    def test_execute_raises_if_step_produces_no_output(self, tmp_path, orchestrator_builder):
        job = MockOrchestratorFactory.make_mock_job("bad_job", output=None)
        # job.run will set _output_dataset = None (the default)
        orchestrator = orchestrator_builder(tmp_path, [job])
        assert orchestrator.jobs_count == 1

        with (
            patch("atlas.io_utils.atlas_dataset.AtlasDataset.from_directory", return_value=AtlasDataset()),
            patch("atlas.orchestrator.current_input_state.CurrentInputState") as MockCIS,
        ):
            mock_cis_instance = MagicMock()
            mock_cis_instance.filter_dataset.return_value = AtlasDataset()
            MockCIS.return_value = mock_cis_instance

            with pytest.raises(RuntimeError, match="bad_job"):
                orchestrator.execute()

    def test_execute_applies_change_sets_after_each_step(self, tmp_path, orchestrator_builder):
        mock_change_set = MagicMock()
        output = MockModuleFactory.make_output()
        output.change_sets = [mock_change_set]

        job = MockOrchestratorFactory.make_mock_job("job")
        job._output_dataset = output
        job.run = lambda ds: None  # run is a no-op; _output_dataset is pre-set

        orchestrator = orchestrator_builder(tmp_path, [job])
        assert orchestrator.jobs_count == 1

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
