"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for Workflow.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pendulum import DateTime, Duration

from atlas import Workflow
from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.io_utils.parameters import ContextParameters
from atlas.core.orchestrator.actionplan.action_plan import ActionPlan
from atlas.core.orchestrator.actionplan.job import ActionPlanJob
from atlas.core.orchestrator.actionplan.parameters import ActionPlanParameters, Task
from atlas.core.orchestrator.module_registry import ModuleRegistry
from atlas.timing import build_datetime
from tests.test_unit.test_orchestrator.orchestrator_factory import (
    ConcreteTaskIterator,
    MockJobBuilder,
    MockTaskBuilder,
    ModuleConfigBuilder,
    OrchestratorConfigBuilder,
)


class ActionPlanMockFactory:
    @staticmethod
    def make_minimal_action_plan(tmp_path) -> ActionPlan:
        params = ActionPlanMockFactory.make_minimal_parameters(tmp_path)
        ap = ActionPlan.__new__(ActionPlan)
        ap.parameters = params
        ap._jobs_count = 0
        ap._priority_queue = []
        return ap

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
        return ActionPlanJob(name, mock_class, {})

    @staticmethod
    def make_minimal_parameters(tmp_path, tasks_yaml="", dataset_path=None, output_path=None):
        """Write a minimal action_plan YAML and return ActionPlanParameters."""
        dataset_dir = dataset_path or (tmp_path / "dataset")
        dataset_dir.mkdir(exist_ok=True)
        output_dir = output_path or (tmp_path / "output")
        output_dir.mkdir(exist_ok=True)

        config = tmp_path / "action_plan.yaml"
        content = f"name: test_action_plan\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\ntasks: []\n"
        if tasks_yaml:
            content = (
                f"name: test_action_plan\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\n{tasks_yaml}"
            )
        config.write_text(content)
        return ActionPlanParameters.from_file(config)


class TestActionPlanPushIterator:
    def test_push_single_job_iterator(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        job = MockJobBuilder().with_name("job").build()
        task = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 1), frequency=Duration(days=1)
            )
            .with_priority(1)
            .build()
        )
        itr = ConcreteTaskIterator(task, job)
        ap._push_iterator(itr)
        assert ap.jobs_count == 1
        assert next(ap.jobs) == job

    def test_push_single_job_iterator_with_multiple_date(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        job = MockJobBuilder().with_name("job").build()
        task = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 3), frequency=Duration(days=1)
            )
            .with_priority(1)
            .build()
        )
        itr = ConcreteTaskIterator(task, job)
        ap._push_iterator(itr)
        assert len(ap._priority_queue) == 1
        assert ap.jobs_count == 3
        assert next(ap.jobs) == job
        assert next(ap.jobs) == job
        assert next(ap.jobs) == job

    def test_push_various_single_job_iterator(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        jobs = [
            MockJobBuilder().with_name("job1").build(),
            MockJobBuilder().with_name("job2").build(),
            MockJobBuilder().with_name("job3").build(),
        ]
        common_task_info = MockTaskBuilder().with_from_until_frequency(
            from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 1), frequency=Duration(days=1)
        )
        ap._push_iterator(ConcreteTaskIterator(common_task_info.with_priority(1).build(), jobs[0]))
        ap._push_iterator(ConcreteTaskIterator(common_task_info.with_priority(3).build(), jobs[2]))
        ap._push_iterator(ConcreteTaskIterator(common_task_info.with_priority(2).build(), jobs[1]))
        assert len(ap._priority_queue) == 3
        assert ap.jobs_count == 3
        assert next(ap.jobs) == jobs[0]
        assert next(ap.jobs) == jobs[1]
        assert next(ap.jobs) == jobs[2]

    def test_push_various_single_job_iterator_with_multiple_date(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        jobs = [MockJobBuilder().with_name("job1").build(), MockJobBuilder().with_name("job2").build()]
        task1 = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 10), frequency=Duration(days=3)
            )
            .with_priority(1)
        ).build()
        task1_len = 4

        task2 = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 11), frequency=Duration(days=5)
            )
            .with_priority(2)
        ).build()
        task2_len = 3

        ap._push_iterator(ConcreteTaskIterator(task1.build(), jobs[0]))
        ap._push_iterator(ConcreteTaskIterator(task2.build(), jobs[1]))

        assert len(ap._priority_queue) == 2
        assert ap.jobs_count == task1_len + task2_len

        expected_job_order = [0, 1, 0, 1, 0, 0, 1]
        for idx, job in enumerate(ap.jobs):
            assert job == jobs[expected_job_order[idx]]

    def test_raise_push_concurrent_jobs_first_execution_date(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        jobs = [MockJobBuilder().with_name("job1").build(), MockJobBuilder().with_name("job2").build()]
        common_task_info = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 1), frequency=Duration(days=1)
            )
            .with_priority(1)
        )

        ap._push_iterator(ConcreteTaskIterator(common_task_info.build(), jobs[0]))
        with pytest.raises(ValueError):
            ap._push_iterator(ConcreteTaskIterator(common_task_info.build(), jobs[1]))

    def test_raise_push_concurrent_jobs(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        jobs = [MockJobBuilder().with_name("job1").build(), MockJobBuilder().with_name("job2").build()]
        task1 = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 5), frequency=Duration(days=1)
            )
            .with_priority(1)
        ).build()

        task2 = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 2), until=DateTime(2000, 1, 5), frequency=Duration(days=2)
            )
            .with_priority(1)
        ).build()

        ap._push_iterator(ConcreteTaskIterator(task1, jobs[0]))
        with pytest.raises(ValueError):
            ap._push_iterator(ConcreteTaskIterator(task2, jobs[1]))

    def test_not_raise_concurrent_jobs_outside_from_until(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        jobs = [MockJobBuilder().with_name("job1").build(), MockJobBuilder().with_name("job2").build()]
        task1 = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 10), frequency=Duration(days=3)
            )
            .with_priority(1)
        ).build()

        task2 = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 11), frequency=Duration(days=5)
            )
            .with_priority(1)
        ).build()

        ap._push_iterator(ConcreteTaskIterator(task1, jobs[0]))
        with pytest.raises(ValueError):
            ap._push_iterator(ConcreteTaskIterator(task2, jobs[1]))


class TestActionPlanPopIterator:
    def test_pop_single_job_iterator(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        job = MockJobBuilder().with_name("job").build()
        task = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 1), frequency=Duration(days=1)
            )
            .with_priority(1)
            .build()
        )
        itr = ConcreteTaskIterator(task, job)

        ap._push_iterator(itr)
        assert len(ap._priority_queue) == 1

        res = ap._pop_iterator()
        assert len(ap._priority_queue) == 0
        assert itr == res

    def test_pop_multi_job_iterator(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        job = MockJobBuilder().with_name("job").build()
        task = (
            MockTaskBuilder()
            .with_from_until_frequency(
                from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 7), frequency=Duration(days=1)
            )
            .with_priority(1)
            .build()
        )
        itr = ConcreteTaskIterator(task, job)

        ap._push_iterator(itr)
        assert len(ap._priority_queue) == 1

        res = ap._pop_iterator()
        assert len(ap._priority_queue) == 0
        assert itr == res

    def test_pop_multiple_iterator(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        jobs = [MockJobBuilder().with_name("job1").build(), MockJobBuilder().with_name("job2").build()]

        common_task_info = MockTaskBuilder().with_from_until_frequency(
            from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 1), frequency=Duration(days=1)
        )

        task1 = common_task_info.with_priority(1).build()
        task2 = common_task_info.with_priority(2).build()

        itr1 = ConcreteTaskIterator(task1, jobs[0])
        itr2 = ConcreteTaskIterator(task2, jobs[1])

        ap._push_iterator(itr1)
        ap._push_iterator(itr2)

        assert len(ap._priority_queue) == 2
        res = ap._pop_iterator()
        assert len(ap._priority_queue) == 1
        assert res == itr1
        res = ap._pop_iterator()
        assert len(ap._priority_queue) == 0
        assert res == itr2


class TestActionPlanAddTask:
    def test_add_task_module(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        task = Task(
            module="PortfolioOptimisation",
            module_parameters_path=ModuleConfigBuilder().build(tmp_path),
            priority=1,
            from_=DateTime(2000, 1, 1),
            until=DateTime(2000, 1, 1),
            frequency=Duration(days=1),
            offset_start_date=Duration(days=1),
            offset_end_date=Duration(days=2),
        )
        ap.add_task(task)
        assert len(ap._priority_queue) == 1
        assert ap._priority_queue[0].task.module == ModuleRegistry.PortfolioOptimisation

    def test_add_task_workflow(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        workflow_config = OrchestratorConfigBuilder().build_workflow(tmp_path)
        workflow = Workflow.from_file(workflow_config)
        task = Task(
            workflow=workflow,
            priority=1,
            from_=DateTime(2000, 1, 1),
            until=DateTime(2000, 1, 1),
            frequency=Duration(days=1),
            offset_start_date=Duration(days=1),
            offset_end_date=Duration(days=2),
        )
        ap.add_task(task)
        assert len(ap._priority_queue) == 1
        assert ap._priority_queue[0].task.workflow == workflow

    def test_add_task_workflow_with_path(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        workflow_config = OrchestratorConfigBuilder().build_workflow(tmp_path)
        workflow = Workflow.from_file(workflow_config)
        task = Task(
            workflow=workflow_config,
            priority=1,
            from_=DateTime(2000, 1, 1),
            until=DateTime(2000, 1, 1),
            frequency=Duration(days=1),
            offset_start_date=Duration(days=1),
            offset_end_date=Duration(days=2),
        )
        ap.add_task(task)
        assert len(ap._priority_queue) == 1
        assert ap._priority_queue[0].task.workflow == workflow_config

    def test_add_various_task(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        task1 = Task(
            module="PortfolioOptimisation",
            module_parameters_path=ModuleConfigBuilder().build(tmp_path),
            priority=1,
            from_=DateTime(2000, 1, 1),
            until=DateTime(2000, 1, 1),
            frequency=Duration(days=1),
            offset_start_date=Duration(days=1),
            offset_end_date=Duration(days=2),
        )
        task2 = Task(
            module="PortfolioOptimisation",
            module_parameters_path=ModuleConfigBuilder().build(tmp_path),
            priority=2,
            from_=DateTime(2000, 1, 1),
            until=DateTime(2000, 1, 1),
            frequency=Duration(days=1),
            offset_start_date=Duration(days=1),
            offset_end_date=Duration(days=2),
        )
        task3 = Task(
            module="PortfolioOptimisation",
            module_parameters_path=ModuleConfigBuilder().build(tmp_path),
            priority=3,
            from_=DateTime(2000, 1, 1),
            until=DateTime(2000, 1, 1),
            frequency=Duration(days=1),
            offset_start_date=Duration(days=1),
            offset_end_date=Duration(days=2),
        )

        partial_task = MockTaskBuilder().with_from_until_frequency(
            from_=DateTime(2000, 1, 1), until=DateTime(2000, 1, 1), frequency=Duration(days=1)
        )
        ap.add_task(task1)
        assert len(ap._priority_queue) == 1
        ap.add_task(task2)
        assert len(ap._priority_queue) == 2
        ap.add_task(task3)
        assert len(ap._priority_queue) == 3


class TestActionPlanFromFile:
    def test_from_file_raises_if_tasks_reference_nonexistent_params(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        config = tmp_path / "actionplan.yaml"
        config.write_text(
            f"name: wf\n"
            f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"tasks:\n"
            f"  - module: PortfolioOptimisation\n"
            f"    module_parameters_path: /nonexistent/path/params.yaml\n"
            f"    from_: '2028-01-01 00:00:00'\n"
            f"    until: '2028-01-03 00:00:00'\n"
            f"    frequency: '1d'\n"
            f"    offset_start_date: '1d'\n"
            f"    offset_end_date: '2d'\n"
        )

        # build_steps will try to open the parameters file -- should raise
        with pytest.raises(Exception):
            ActionPlan.from_file(config)


class TestActionPlanRepresentation:
    def test_repr_representation(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        params_file = tmp_path / "params.yaml"
        params_file.write_text(
            "temporal:\n"
            "  start_date: '2028-09-27 00:00:00'\n"
            "  end_date: '2028-09-28 00:00:00'\n"
            "  execution_date: '2028-09-26 12:00:00'\n"
            "solver:\n"
            "  solver_name: GLOP\n"
        )

        config = tmp_path / "action_plan.yaml"
        config.write_text(
            f"name: test_action_plan\n"
            f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"tasks:\n"
            f"  - module: MarketClearing\n"
            f"    module_parameters_path: {params_file}\n"
            f"    from_: '2028-01-01 00:00:00'\n"
            f"    until: '2028-01-03 00:00:00'\n"
            f"    frequency: '1d'\n"
            f"    offset_start_date: '1d'\n"
            f"    offset_end_date: '2d'\n"
        )

        action_plan = ActionPlan.from_file(config)
        result = repr(action_plan)
        assert "ActionPlan 'test_action_plan'" in result
        assert "1 task" in result
        assert "3 steps" in result


# FIXME factorize this part in test_abstract_orchestrator.py -- those test must be the same for any orchestrator
class TestActionPlanContextParameters:
    @staticmethod
    def create_config(tmp_path, context: str, module_parameters: str | None = None) -> Path:
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        params_file = tmp_path / "params.yaml"
        if module_parameters is None:
            params_file.write_text(
                "temporal:\n"
                "  start_date: '2028-09-27 00:00:00'\n"
                "  end_date: '2028-09-28 00:00:00'\n"
                "  execution_date: '2028-09-26 12:00:00'\n"
            )
        else:
            params_file.write_text(module_parameters)

        config = tmp_path / "action_plan.yaml"
        config.write_text(
            "name: test_action_plan\n" + context + f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"tasks:\n"
            f"  - module: MarketClearing\n"
            f"    module_parameters_path: {params_file}\n"
            f"    from_: '2028-09-26 00:00:00'\n"
            f"    until: '2028-09-27 00:00:00'\n"
            f"    frequency: '1d'\n"
            f"    offset_start_date: '1d'\n"
            f"    offset_end_date: '2d'\n"
        )
        return config

    def test_context_parameters(self, tmp_path):
        context = (
            "context:\n"
            "  default:\n"
            "    foo: 'default_value'\n"
            "    list_foo:\n"
            "       foo1: 1\n"
            "       foo2: 2\n"
            "  forced:\n"
            "    foo: 'forced_value'\n"
            "    list_foo:\n"
            "       foo2: 20\n"
            "       foo4: 40\n"
        )
        config = TestActionPlanContextParameters.create_config(tmp_path, context)
        action_plan = ActionPlan.from_file(config)
        assert action_plan.parameters.context.default["foo"] == "default_value"
        assert action_plan.parameters.context.default["list_foo"] == {"foo1": 1, "foo2": 2}
        assert action_plan.parameters.context.forced["foo"] == "forced_value"
        assert action_plan.parameters.context.forced["list_foo"] == {"foo2": 20, "foo4": 40}

    def test_context_parameters_with_additional_context(self, tmp_path):
        context_file = (
            "context:\n"
            "  default:\n"
            "    foo: 'default_value_file'\n"
            "    file_exclusive: 'default_value_file_exclusive'\n"
            "  forced:\n"
            "    foo: 'forced_value_file'\n"
            "    file_exclusive: 'forced_value_file_exclusive'\n"
        )

        overriding_context = ContextParameters()
        overriding_context.default = {
            "foo": "default_value_overriding",
            "override_exclusive": "default_value_override_exclusive",
        }
        overriding_context.forced = {
            "foo": "forced_value_overriding",
            "override_exclusive": "forced_value_override_exclusive",
        }

        action_plan = ActionPlan.from_file(
            TestActionPlanContextParameters.create_config(tmp_path, context_file), overriding_context
        )
        assert action_plan.parameters.context.default["foo"] == "default_value_overriding"
        assert action_plan.parameters.context.forced["foo"] == "forced_value_overriding"
        assert action_plan.parameters.context.default["override_exclusive"] == "default_value_override_exclusive"
        assert action_plan.parameters.context.forced["override_exclusive"] == "forced_value_override_exclusive"
        assert action_plan.parameters.context.default["file_exclusive"] == "default_value_file_exclusive"
        assert action_plan.parameters.context.forced["file_exclusive"] == "forced_value_file_exclusive"

    def test_default_context_on_empty_parameter(self, tmp_path):
        context = (
            "context:\n"
            "  default:\n"
            "    temporal:\n"
            "      start_date: '2028-09-27 00:00:00'\n"
            "      end_date: '2028-09-28 00:00:00'\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
        )
        action_plan = ActionPlan.from_file(
            TestActionPlanContextParameters.create_config(tmp_path, context, module_parameters="")
        )

        job = next(action_plan.jobs)
        assert job.parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert job.parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert job.parameters.temporal.execution_date == build_datetime("2028-09-26 00:00:00")

    def test_forced_context_on_empty_parameter(self, tmp_path):
        context = (
            "context:\n"
            "  forced:\n"
            "    temporal:\n"
            "      start_date: '2028-09-27 00:00:00'\n"
            "      end_date: '2028-09-28 00:00:00'\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
        )
        action_plan = ActionPlan.from_file(
            TestActionPlanContextParameters.create_config(tmp_path, context, module_parameters="")
        )

        job = next(action_plan.jobs)
        assert job.parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert job.parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert job.parameters.temporal.execution_date == build_datetime("2028-09-26 00:00:00")

    def test_default_context_on_partial_parameter(self, tmp_path):
        context = (
            "context:\n"
            "  default:\n"
            "    temporal:\n"
            "      start_date: 'wrong-date'\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
        )
        module_parameters = "temporal:\n  start_date: '2028-09-27 00:00:00'\n  end_date: '2028-09-28 00:00:00'\n"
        action_plan = ActionPlan.from_file(
            TestActionPlanContextParameters.create_config(tmp_path, context, module_parameters)
        )

        job = next(action_plan.jobs)
        assert job.parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert job.parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert job.parameters.temporal.execution_date == build_datetime("2028-09-26 00:00:00")

    def test_forced_context_on_partial_parameter(self, tmp_path):
        context = (
            "context:\n"
            "  forced:\n"
            "    temporal:\n"
            "      start_date: '2028-09-27 00:00:00'\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
        )
        module_parameters = "temporal:\n  start_date: 'wrong-date'\n  end_date: '2028-09-28 00:00:00'\n"
        action_plan = ActionPlan.from_file(
            TestActionPlanContextParameters.create_config(tmp_path, context, module_parameters)
        )

        job = next(action_plan.jobs)
        assert job.parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert job.parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert job.parameters.temporal.execution_date == build_datetime("2028-09-26 00:00:00")

    def test_context_forced_override_default(self, tmp_path):
        context = (
            "context:\n"
            "  default:\n"
            "    temporal:\n"
            "      start_date: 'wrong-date-context'\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
            "  forced:\n"
            "    temporal:\n"
            "      start_date: '2028-09-27 00:00:00'\n"
            "      end_date: '2028-09-28 00:00:00'\n"
        )
        module_parameters = "temporal:\n  start_date: 'wrong-date'\n  end_date: 'wrong-date'\n"
        action_plan = ActionPlan.from_file(
            TestActionPlanContextParameters.create_config(tmp_path, context, module_parameters)
        )

        job = next(action_plan.jobs)
        assert job.parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert job.parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert job.parameters.temporal.execution_date == build_datetime("2028-09-26 00:00:00")

    def test_error_on_incomplete_module_parameter(self, tmp_path):
        context = (
            "context:\n"
            "  default:\n"
            "    temporal:\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
            "  forced:\n"
            "    temporal:\n"
            "      start_date: '2028-09-27 00:00:00'\n"
        )
        # build_steps will try to open the parameters file -- should raise
        with pytest.raises(Exception):
            ActionPlan.from_file(TestActionPlanContextParameters.create_config(tmp_path, context, module_parameters=""))


class TestActionPlanPathFromActionPlan:
    def test_dataset_loaded_relative_to_action_plan_when_path_from_action_plan_true(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        config = tmp_path / "action_plan.yaml"
        config.write_text(
            "name: test_action_plan\n"
            "dataset_path: dataset\n"
            "output_dataset_path: output\n"
            "path_from_action_plan: true\n"
            "tasks: []\n"
        )

        action_plan = ActionPlan.from_file(config)

        with (
            patch("atlas.core.orchestrator.current_input_state.CurrentInputState.from_directory") as mock_from_dir,
            patch.object(Path, "mkdir", return_value=None),
            patch.object(AtlasDataset, "to_directory"),
        ):
            mock_cis = MagicMock()
            mock_cis.data = AtlasDataset()
            mock_from_dir.return_value = mock_cis
            action_plan.execute()
            mock_from_dir.assert_called_once_with(tmp_path / "dataset")

    def test_dataset_loaded_relative_to_cwd_when_path_from_action_plan_false(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        config = tmp_path / "action_plan.yaml"
        config.write_text(
            f"name: test_action_plan\n"
            f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"path_from_action_plan: false\n"
            f"tasks: []\n"
        )

        action_plan = ActionPlan.from_file(config)

        with (
            patch("atlas.core.orchestrator.current_input_state.CurrentInputState.from_directory") as mock_from_dir,
            patch.object(AtlasDataset, "to_directory"),
        ):
            mock_cis = MagicMock()
            mock_cis.data = AtlasDataset()
            mock_from_dir.return_value = mock_cis
            action_plan.execute()
            mock_from_dir.assert_called_once_with(dataset_dir)

    def test_step_output_dir_resolved_relative_to_action_plan(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        params_file = tmp_path / "params.yaml"
        params_file.write_text(
            "temporal:\n"
            "  start_date: '2028-09-27 00:00:00'\n"
            "  end_date: '2028-09-28 00:00:00'\n"
            "  execution_date: '2028-09-26 12:00:00'\n"
        )

        config = tmp_path / "action_plan.yaml"
        config.write_text(
            f"name: test_action_plan\n"
            f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"path_from_action_plan: true\n"
            f"output_dir: results\n"
            f"tasks:\n"
            f"  - module: MarketClearing\n"
            f"    module_parameters_path: {params_file}\n"
            f"    from_: '2028-01-01 00:00:00'\n"
            f"    until: '2028-01-03 00:00:00'\n"
            f"    frequency: '1d'\n"
            f"    offset_start_date: '1d'\n"
            f"    offset_end_date: '2d'\n"
        )

        action_plan = ActionPlan.from_file(config)
        step = next(action_plan.jobs)

        assert step.parameters.output.output_dir == Path(
            tmp_path / "results" / "MarketClearing" / "2028-01-01T00:00:00+00:00"
        )
