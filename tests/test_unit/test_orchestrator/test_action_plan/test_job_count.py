"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import pytest
from pendulum import DateTime, Duration

from atlas.orchestrator.actionplan.action_plan import ActionPlan
from atlas.orchestrator.actionplan.job import WorkflowTaskJobsGenerator
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters, TaskWorkflow
from atlas.orchestrator.workflow.workflow import Workflow
from tests.test_unit.test_orchestrator.orchestrator_factory import ModuleConfigBuilder
from atlas.orchestrator.actionplan.parameters import TaskModule

def _write_workflow_with_n_steps(tmp_path: Path, dataset_dir: Path, n_steps: int, name: str = "sub_workflow") -> Path:
    """Write a minimal workflow config with `n_steps` MarketClearing steps."""
    steps = "".join(
        f"  - name: step{i}\n"
        f"    module: MarketClearing\n"
        f"    parameters:\n"
        f"      temporal:\n"
        f"        start_date: '2028-09-27 00:00:00'\n"
        f"        end_date: '2028-09-28 00:00:00'\n"
        f"        execution_date: '2028-09-26 12:00:00'\n"
        for i in range(n_steps)
    )
    config = tmp_path / f"{name}.yaml"
    config.write_text(f"name: {name}\ndataset_path: {dataset_dir}\nsteps:\n{steps}")
    return config


def _make_action_plan(tmp_path: Path) -> ActionPlan:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir(exist_ok=True)
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)

    config = tmp_path / "action_plan.yaml"
    config.write_text(
        f"name: test_action_plan\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\ntasks: []\n"
    )
    return ActionPlan(ActionPlanParameters.from_file(config))


class TestActionPlanJobsCountContract:
    """`jobs_count` must always equal the number of jobs `execute()` runs, i.e. len(list(jobs))."""

    def test_jobs_count_matches_actual_jobs_for_module_task(self, tmp_path):
        ap = _make_action_plan(tmp_path)
        ap.add_task(
            TaskModule(
                module="PortfolioOptimisation",
                parameters=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 3),
                frequency=Duration(days=1),
            )
        )

        actual_jobs_executed = sum(1 for _ in ap.jobs)
        assert actual_jobs_executed == 3  # one job per day, from Jan 1st to Jan 3rd
        assert ap.jobs_count == actual_jobs_executed

    @pytest.mark.parametrize("n_steps", [1, 2, 3, 5])
    def test_jobs_count_matches_actual_jobs_for_workflow_task(self, tmp_path, n_steps):
        """
        A TaskWorkflow wrapping a workflow with `n_steps` steps and run over 3 iterations
        must produce 3 * n_steps jobs, and jobs_count must reflect that.

        This currently fails for n_steps != 1: jobs_count only counts iterations (3),
        regardless of how many jobs each iteration of the sub-workflow actually yields.
        """
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir(exist_ok=True)

        workflow_config = _write_workflow_with_n_steps(tmp_path, dataset_dir, n_steps)
        workflow = Workflow.from_file(workflow_config)
        assert workflow.jobs_count == n_steps  # sanity check on the sub-workflow itself

        ap = _make_action_plan(tmp_path)
        ap.add_task(
            TaskWorkflow(
                workflow=workflow,
                priority=1,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 3),
                frequency=Duration(days=1),
            )
        )

        actual_jobs_executed = sum(1 for _ in ap.jobs)
        assert actual_jobs_executed == 3 * n_steps # one job per day (from Jan 1st to Jan 3rd) by step
        assert ap.jobs_count == actual_jobs_executed

    @pytest.mark.parametrize("n_steps", [1, 2, 3, 5])
    def test_jobs_count_matches_actual_jobs_for_mixed_tasks(self, tmp_path, n_steps):
        """A more realistic action plan mixing a module task and a multi-step workflow task."""

        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir(exist_ok=True)

        workflow_config = _write_workflow_with_n_steps(tmp_path, dataset_dir, n_steps)
        workflow = Workflow.from_file(workflow_config)

        ap = _make_action_plan(tmp_path)
        ap.add_task(
            TaskModule(
                name="module_task",
                module="PortfolioOptimisation",
                parameters=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 2),
                frequency=Duration(days=1),
            )
        )
        ap.add_task(
            TaskWorkflow(
                name="workflow_task",
                workflow=workflow,
                priority=2,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 2),
                frequency=Duration(days=1),
            )
        )

        actual_jobs_executed = sum(1 for _ in ap.jobs)
        # 2 iterations * 1 job (module) + 2 iterations * n_steps jobs (workflow) = 8
        assert actual_jobs_executed == 2*1 + 2*n_steps

        assert ap.jobs_count == actual_jobs_executed


class TestWorkflowTaskJobsGeneratorLenVsJobsProduced:
    """Isolates the root cause: TaskJobsGenerator.__len__ counts iterations, not jobs produced."""

    @pytest.mark.parametrize("n_steps", [1, 2, 4])
    def test_len_should_reflect_total_jobs_produced_across_all_iterations(self, tmp_path, n_steps):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir(exist_ok=True)
        workflow_config = _write_workflow_with_n_steps(tmp_path, dataset_dir, n_steps)
        workflow = Workflow.from_file(workflow_config)

        task = TaskWorkflow(
            workflow=workflow,
            priority=1,
            from_=DateTime(2000, 1, 1),
            until=DateTime(2000, 1, 3),
            frequency=Duration(days=1),
        )
        generator = WorkflowTaskJobsGenerator(task, workflow.parameters, tmp_path)

        total_jobs_actually_produced = sum(
            len(generator.build_jobs(iteration)) for iteration in range(1, len(generator) + 1)
        )
        assert total_jobs_actually_produced == 3 * n_steps
        assert len(generator) == total_jobs_actually_produced