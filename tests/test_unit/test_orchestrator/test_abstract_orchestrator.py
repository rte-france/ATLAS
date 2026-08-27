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
from atlas.orchestrator.actionplan.job import TaskJobsGenerator, TaskIterationPriority
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters
from atlas.orchestrator.workflow.workflow import Workflow
from tests.test_unit.test_orchestrator.orchestrator_factory import (
    ConcreteTaskGenerator,
    ConcreteOrchestrator,
    ConcreteOrchestratorParameters,
    MockOutPutBuilder,
    MockJobBuilder,
    MockTaskBuilder,
    OrchestratorConfigBuilder
)

class _OrchestratorBuilder():
    @staticmethod
    def make_mock_orchestrator(
        tmp_path, jobs: list, yaml_context: str = "", overall_context: ContextParameters | None = None
    ) -> ConcreteOrchestrator:
        config = OrchestratorConfigBuilder().with_context(yaml_context).build(tmp_path)
        params = ConcreteOrchestratorParameters.from_file(config)
        orchestrator = ConcreteOrchestrator.__new__(ConcreteOrchestrator)
        orchestrator.parameters = params
        if overall_context is not None:
            orchestrator.parameters.context.use(overall_context)
        orchestrator._jobs = jobs
        return orchestrator


    @staticmethod
    def make_mock_workflow(
        tmp_path, jobs: list, yaml_context: str = "", overall_context: ContextParameters | None = None
    ) -> Workflow:
        config = OrchestratorConfigBuilder().with_context(yaml_context).build_workflow(tmp_path)
        params = WorkflowParameters.from_file(config, overall_context)
        workflow = Workflow.__new__(Workflow)
        workflow.parameters = params
        workflow._jobs = jobs
        return workflow


    @staticmethod
    def make_mock_action_plan(
        tmp_path, jobs: list, yaml_context: str = "", overall_context: ContextParameters | None = None
    ) -> ActionPlan:
        config = OrchestratorConfigBuilder().with_context(yaml_context).build_action_plan(tmp_path)
        params = ActionPlanParameters.from_file(config, overall_context)
        action_plan = ActionPlan.__new__(ActionPlan)
        action_plan.parameters = params
        job_generators: list[TaskJobsGenerator] = []
        for priority, job in enumerate(jobs):
            task = MockTaskBuilder().with_priority(priority).build()
            job_generators.append(ConcreteTaskGenerator(task, job))
        action_plan._task_job_generators = job_generators
        return action_plan


CONCRETE_ORCHESTRATOR_BUILDERS = [
    _OrchestratorBuilder.make_mock_orchestrator,
    _OrchestratorBuilder.make_mock_action_plan,
    _OrchestratorBuilder.make_mock_workflow,
]


@pytest.fixture(params=CONCRETE_ORCHESTRATOR_BUILDERS)
def orchestrator_builder(request):
    return request.param


class TestOrchestratorExecute:
    def test_execute_runs_all_steps_in_order(self, tmp_path, orchestrator_builder):
        call_order = []
        output1 = MockOutPutBuilder().build()
        output2 = MockOutPutBuilder().build()

        def run1(ds):
            call_order.append("job1")
            job1._output_dataset = output1

        def run2(ds):
            call_order.append("job2")
            job2._output_dataset = output2

        job1 = MockJobBuilder().with_name("job1").build()
        job1.module.run = MagicMock(side_effect=lambda ds, params: output1)
        job1.run = run1

        job2 = MockJobBuilder().with_name("job2").build()
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
        job = MockJobBuilder().with_name("bad_job").with_output(None).build()
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
        output = MockOutPutBuilder().with_change_sets([mock_change_set]).build()

        job = MockJobBuilder().with_name("job").build()
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
        mock_output = MockOutPutBuilder().build()
        job1 = MockJobBuilder().with_name("job1").build()
        job2 = MockJobBuilder().with_name("job2").with_output(mock_output).build()
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
