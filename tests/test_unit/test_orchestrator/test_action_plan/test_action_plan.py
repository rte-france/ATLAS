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
from atlas.orchestrator.module_registry import ModuleRegistry
from tests.test_unit.test_orchestrator.orchestrator_factory import MockJobBuilder, MockTaskBuilder, ConcreteTaskGenerator, MockModuleBuilder, OrchestratorConfigBuilder, ModuleConfigBuilder

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.io_utils.parameters import ContextParameters
from atlas.orchestrator.actionplan.action_plan import ActionPlan
from atlas.orchestrator.actionplan.job import ActionPlanJob
from atlas.orchestrator.actionplan.parameters import ActionPlanParameters, TaskModule, TaskWorkflow
from atlas.timing import build_datetime


class ActionPlanMockFactory:
    @staticmethod
    def make_minimal_action_plan(tmp_path) -> ActionPlan:
        params = ActionPlanMockFactory.make_minimal_parameters(tmp_path)
        ap = ActionPlan(params)
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


class TestActionPlanAddTask:
    def test_add_task_module(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        task = TaskModule(
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 1),
                frequency=Duration(days=1),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        )
        ap.add_task(task)
        assert len(ap._task_job_generators) == 1
        assert ap._task_job_generators[0]._task.module == ModuleRegistry.PortfolioOptimisation

    def test_add_task_workflow(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        workflow_config = OrchestratorConfigBuilder().build_workflow(tmp_path)
        workflow = Workflow.from_file(workflow_config)
        task = TaskWorkflow(
                workflow=workflow,
                priority=1,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 1),
                frequency=Duration(days=1),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        )
        ap.add_task(task)
        assert len(ap._task_job_generators) == 1
        assert ap._task_job_generators[0]._task.workflow == workflow

    def test_add_task_workflow_with_path(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        workflow_config = OrchestratorConfigBuilder().build_workflow(tmp_path)
        workflow = Workflow.from_file(workflow_config)
        task = TaskWorkflow(
                workflow=workflow_config,
                priority=1,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 1),
                frequency=Duration(days=1),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        )
        ap.add_task(task)
        assert len(ap._task_job_generators) == 1
        assert ap._task_job_generators[0]._task.workflow == workflow_config

    def test_add_various_task(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        ap.add_task(TaskModule(
                name="1",
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 1),
                frequency=Duration(days=1),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        ))
        ap.add_task(TaskModule(
                name="2",
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=2,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 1),
                frequency=Duration(days=1),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        ))
        ap.add_task(TaskModule(
                name="3",
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=3,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 1),
                frequency=Duration(days=1),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        ))
        assert ap.jobs_count == 3
        expected_job_order = ["task 1 iteration 1",
                              "task 2 iteration 1",
                              "task 3 iteration 1"]
        for idx, job in enumerate(ap.jobs):
            assert job.name == expected_job_order[idx]

    def test_add_various_task_with_multiple_date(self, tmp_path):
        ap = ActionPlanMockFactory.make_minimal_action_plan(tmp_path)
        ap.add_task(TaskModule(
                name="1",
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 10),
                frequency=Duration(days=3),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        ))
        ap.add_task(TaskModule(
                name="2",
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=2,
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 11),
                frequency=Duration(days=5),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        ))
        assert ap.jobs_count == 7
        expected_job_order = ["task 1 iteration 1",
                              "task 2 iteration 1",
                              "task 1 iteration 2",
                              "task 2 iteration 2",
                              "task 1 iteration 3",
                              "task 1 iteration 4",
                              "task 2 iteration 3"]
        for idx, job in enumerate(ap.jobs):
            assert job.name == expected_job_order[idx]


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
            f"    parameters_path: /nonexistent/path/params.yaml\n"
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
            f"    parameters_path: {params_file}\n"
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
            f"    parameters_path: {params_file}\n"
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
        action_plan = ActionPlan.from_file(TestActionPlanContextParameters.create_config(tmp_path, context, module_parameters))

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
        action_plan = ActionPlan.from_file(TestActionPlanContextParameters.create_config(tmp_path, context, module_parameters))

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
        action_plan = ActionPlan.from_file(TestActionPlanContextParameters.create_config(tmp_path, context, module_parameters))

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
            f"tasks: []\n"
        )

        action_plan = ActionPlan.from_file(config)

        with (
            patch("atlas.orchestrator.current_input_state.CurrentInputState.from_directory") as mock_from_dir,
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
            patch("atlas.orchestrator.current_input_state.CurrentInputState.from_directory") as mock_from_dir,
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
            f"    parameters_path: {params_file}\n"
            f"    from_: '2028-01-01 00:00:00'\n"
            f"    until: '2028-01-03 00:00:00'\n"
            f"    frequency: '1d'\n"
            f"    offset_start_date: '1d'\n"
            f"    offset_end_date: '2d'\n"
        )

        action_plan = ActionPlan.from_file(config)
        step = next(action_plan.jobs)

        assert step.parameters.output.output_dir == Path(tmp_path / 'results' / 'MarketClearing' / '2028-01-01T00:00:00+00:00')
