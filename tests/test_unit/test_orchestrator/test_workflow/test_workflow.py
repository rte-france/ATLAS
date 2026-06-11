"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for Workflow.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas import WorkflowJob
from atlas.core.io_utils.atlas_dataset import AtlasDataset
from atlas.core.io_utils.parameters import ContextParameters
from atlas.core.orchestrator.workflow.workflow import Workflow
from atlas.timing import build_datetime
from tests.test_unit.test_orchestrator.orchestrator_factory import MockJobBuilder, OrchestratorConfigBuilder


class TestWorkflowAddStep:
    @pytest.fixture
    def empty_workflow(self, tmp_path):
        conf = OrchestratorConfigBuilder().build_workflow(tmp_path)
        params = Workflow.from_file(conf)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf._jobs = []
        return wf

    @pytest.fixture(autouse=True)
    def job_builder(self):
        self.job_builder = MockJobBuilder().with_job_class(WorkflowJob)

    def test_add_single_step(self, tmp_path, empty_workflow):
        step = self.job_builder.with_name("s1").build()
        empty_workflow.add_job(step)

        assert empty_workflow.jobs_count == 1
        assert next(empty_workflow.jobs) is step

    def test_add_list_of_steps(self, tmp_path, empty_workflow):
        steps = [self.job_builder.with_name(f"s{i}").build() for i in range(3)]
        empty_workflow.add_job(steps)

        assert empty_workflow.jobs_count == 3
        for original, stored in zip(steps, empty_workflow.jobs):
            assert stored is original

    def test_add_invalid_type_raises_type_error(self, tmp_path, empty_workflow):
        with pytest.raises(TypeError):
            empty_workflow.add_job("not_a_step")

    def test_add_list_with_invalid_item_raises_type_error(self, tmp_path, empty_workflow):
        valid_step = self.job_builder.with_name("s1").build()
        with pytest.raises(TypeError):
            empty_workflow.add_job([valid_step, "not_a_step"])

    def test_steps_appended_in_order(self, tmp_path, empty_workflow):
        s1 = self.job_builder.with_name("first").build()
        s2 = self.job_builder.with_name("second").build()
        empty_workflow.add_job(s1)
        empty_workflow.add_job(s2)

        jobs = empty_workflow.jobs
        assert next(jobs) is s1
        assert next(jobs) is s2


class TestWorkflowFromFile:
    def test_from_file_raises_if_steps_reference_nonexistent_params(self, tmp_path):
        config = (
            OrchestratorConfigBuilder()
            .with_any("steps:\n  - module: PortfolioOptimisation\n    parameters_path: /nonexistent/path/params.yaml\n")
            .build(tmp_path)
        )

        # build_steps will try to open the parameters file -- should raise
        with pytest.raises(Exception):
            Workflow.from_file(config)


class TestWorkflowRepresentation:
    def test_repr_representation(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text(
            "temporal:\n"
            "  start_date: '2028-09-27 00:00:00'\n"
            "  end_date: '2028-09-28 00:00:00'\n"
            "  execution_date: '2028-09-26 12:00:00'\n"
            "solver:\n"
            "  solver_name: GLOP\n"
        )
        config = (
            OrchestratorConfigBuilder()
            .with_name("test_workflow")
            .with_any(f"steps:\n  - module: MarketClearing\n    parameters_path: {params_file}\n")
            .build(tmp_path)
        )

        workflow = Workflow.from_file(config)
        result = repr(workflow)
        assert "Workflow 'test_workflow'" in result
        assert "1 step" in result


class TestWorkflowContextParameters:
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

        config = tmp_path / "workflow.yaml"
        config.write_text(
            "name: test_workflow\n" + context + f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"steps:\n"
            f"  - module: MarketClearing\n"
            f"    parameters_path: {params_file}\n"
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
        config = TestWorkflowContextParameters.create_config(tmp_path, context)
        workflow = Workflow.from_file(config)
        assert workflow.parameters.context.default["foo"] == "default_value"
        assert workflow.parameters.context.default["list_foo"] == {"foo1": 1, "foo2": 2}
        assert workflow.parameters.context.forced["foo"] == "forced_value"
        assert workflow.parameters.context.forced["list_foo"] == {"foo2": 20, "foo4": 40}

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

        workflow = Workflow.from_file(
            TestWorkflowContextParameters.create_config(tmp_path, context_file), overriding_context
        )
        assert workflow.parameters.context.default["foo"] == "default_value_overriding"
        assert workflow.parameters.context.forced["foo"] == "forced_value_overriding"
        assert workflow.parameters.context.default["override_exclusive"] == "default_value_override_exclusive"
        assert workflow.parameters.context.forced["override_exclusive"] == "forced_value_override_exclusive"
        assert workflow.parameters.context.default["file_exclusive"] == "default_value_file_exclusive"
        assert workflow.parameters.context.forced["file_exclusive"] == "forced_value_file_exclusive"

    def test_default_context_on_empty_parameter(self, tmp_path):
        context = (
            "context:\n"
            "  default:\n"
            "    temporal:\n"
            "      start_date: '2028-09-27 00:00:00'\n"
            "      end_date: '2028-09-28 00:00:00'\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
        )
        workflow = Workflow.from_file(
            TestWorkflowContextParameters.create_config(tmp_path, context, module_parameters="")
        )

        assert next(workflow.jobs).parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert next(workflow.jobs).parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert next(workflow.jobs).parameters.temporal.execution_date == build_datetime("2028-09-26 12:00:00")

    def test_forced_context_on_empty_parameter(self, tmp_path):
        context = (
            "context:\n"
            "  forced:\n"
            "    temporal:\n"
            "      start_date: '2028-09-27 00:00:00'\n"
            "      end_date: '2028-09-28 00:00:00'\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
        )
        workflow = Workflow.from_file(
            TestWorkflowContextParameters.create_config(tmp_path, context, module_parameters="")
        )

        assert next(workflow.jobs).parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert next(workflow.jobs).parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert next(workflow.jobs).parameters.temporal.execution_date == build_datetime("2028-09-26 12:00:00")

    def test_default_context_on_partial_parameter(self, tmp_path):
        context = (
            "context:\n"
            "  default:\n"
            "    temporal:\n"
            "      start_date: 'wrong-date'\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
        )
        module_parameters = "temporal:\n  start_date: '2028-09-27 00:00:00'\n  end_date: '2028-09-28 00:00:00'\n"
        workflow = Workflow.from_file(TestWorkflowContextParameters.create_config(tmp_path, context, module_parameters))

        assert next(workflow.jobs).parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert next(workflow.jobs).parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert next(workflow.jobs).parameters.temporal.execution_date == build_datetime("2028-09-26 12:00:00")

    def test_forced_context_on_partial_parameter(self, tmp_path):
        context = (
            "context:\n"
            "  forced:\n"
            "    temporal:\n"
            "      start_date: '2028-09-27 00:00:00'\n"
            "      execution_date: '2028-09-26 12:00:00'\n"
        )
        module_parameters = "temporal:\n  start_date: 'wrong-date'\n  end_date: '2028-09-28 00:00:00'\n"
        workflow = Workflow.from_file(TestWorkflowContextParameters.create_config(tmp_path, context, module_parameters))

        assert next(workflow.jobs).parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert next(workflow.jobs).parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert next(workflow.jobs).parameters.temporal.execution_date == build_datetime("2028-09-26 12:00:00")

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
        workflow = Workflow.from_file(TestWorkflowContextParameters.create_config(tmp_path, context, module_parameters))

        assert next(workflow.jobs).parameters.temporal.start_date == build_datetime("2028-09-27 00:00:00")
        assert next(workflow.jobs).parameters.temporal.end_date == build_datetime("2028-09-28 00:00:00")
        assert next(workflow.jobs).parameters.temporal.execution_date == build_datetime("2028-09-26 12:00:00")

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
            Workflow.from_file(TestWorkflowContextParameters.create_config(tmp_path, context, module_parameters=""))


class TestWorkflowPathFromWorkflow:
    def test_dataset_loaded_relative_to_workflow_when_path_from_workflow_true(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        config = tmp_path / "workflow.yaml"
        config.write_text(
            "name: test_workflow\n"
            "dataset_path: dataset\n"
            "output_dataset_path: output\n"
            "path_from_workflow: true\n"
            "steps: []\n"
        )

        workflow = Workflow.from_file(config)

        with (
            patch("atlas.core.orchestrator.current_input_state.CurrentInputState.from_directory") as mock_from_dir,
            patch.object(Path, "mkdir", return_value=None),
            patch.object(AtlasDataset, "to_directory"),
        ):
            mock_cis = MagicMock()
            mock_cis.data = AtlasDataset()
            mock_from_dir.return_value = mock_cis
            workflow.execute()
            mock_from_dir.assert_called_once_with(tmp_path / "dataset")

    def test_dataset_loaded_relative_to_cwd_when_path_from_workflow_false(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        config = tmp_path / "workflow.yaml"
        config.write_text(
            f"name: test_workflow\n"
            f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"path_from_workflow: false\n"
            f"steps: []\n"
        )

        workflow = Workflow.from_file(config)

        with (
            patch("atlas.core.orchestrator.current_input_state.CurrentInputState.from_directory") as mock_from_dir,
            patch.object(AtlasDataset, "to_directory"),
        ):
            mock_cis = MagicMock()
            mock_cis.data = AtlasDataset()
            mock_from_dir.return_value = mock_cis
            workflow.execute()
            mock_from_dir.assert_called_once_with(dataset_dir)

    def test_step_output_dir_resolved_relative_to_workflow(self, tmp_path):
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

        config = tmp_path / "workflow.yaml"
        config.write_text(
            f"name: test_workflow\n"
            f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"path_from_workflow: true\n"
            f"output_dir: results\n"
            f"steps:\n"
            f"  - module: MarketClearing\n"
            f"    parameters_path: {params_file}\n"
        )

        workflow = Workflow.from_file(config)
        step = next(workflow.jobs)

        assert step.parameters.output.output_dir == tmp_path / "results" / "MarketClearing"
