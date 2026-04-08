"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for Workflow.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.orchestrator.workflow.parameters import WorkflowParameters
from atlas.orchestrator.workflow.job import WorkflowJob
from atlas.orchestrator.workflow.workflow import Workflow


def _make_workflow_step(name="job", output=None):
    """Return a WorkflowJob with a mock module that returns *output*."""
    mock_instance = MagicMock()
    mock_instance.run.return_value = output
    mock_instance.get_business_model_class_used.return_value = []
    mock_instance.get_filters.return_value = None

    mock_class = MagicMock(return_value=mock_instance)
    return WorkflowJob(name, mock_class, {})


def _make_workflow_parameters(tmp_path, steps_yaml="", dataset_path=None, output_path=None):
    """Write a minimal workflow YAML and return WorkflowParameters."""
    dataset_dir = dataset_path or (tmp_path / "dataset")
    dataset_dir.mkdir(exist_ok=True)
    output_dir = output_path or (tmp_path / "output")
    output_dir.mkdir(exist_ok=True)

    config = tmp_path / "workflow.yaml"
    content = f"name: test_workflow\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\nsteps: []\n"
    if steps_yaml:
        content = f"name: test_workflow\ndataset_path: {dataset_dir}\noutput_dataset_path: {output_dir}\n{steps_yaml}"
    config.write_text(content)
    return WorkflowParameters.from_file(config)


class TestWorkflowAddStep:
    def test_add_single_step(self, tmp_path):
        params = _make_workflow_parameters(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf.generic_module_parameters = {}
        wf._jobs = []

        step = _make_workflow_step("s1")
        wf.add_job(step)

        assert len(wf.jobs) == 1
        assert wf.jobs[0] is step

    def test_add_list_of_steps(self, tmp_path):
        params = _make_workflow_parameters(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf.generic_module_parameters = {}
        wf._jobs = []

        steps = [_make_workflow_step(f"s{i}") for i in range(3)]
        wf.add_job(steps)

        assert len(wf.jobs) == 3
        for original, stored in zip(steps, wf.jobs):
            assert stored is original

    def test_add_invalid_type_raises_type_error(self, tmp_path):
        params = _make_workflow_parameters(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf.generic_module_parameters = {}
        wf._jobs = []

        with pytest.raises(TypeError):
            wf.add_job("not_a_step")

    def test_add_list_with_invalid_item_raises_type_error(self, tmp_path):
        params = _make_workflow_parameters(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf.generic_module_parameters = {}
        wf._jobs = []

        valid_step = _make_workflow_step("s1")
        with pytest.raises(TypeError):
            wf.add_job([valid_step, "not_a_step"])

    def test_steps_appended_in_order(self, tmp_path):
        params = _make_workflow_parameters(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf.generic_module_parameters = {}
        wf._jobs = []

        s1 = _make_workflow_step("first")
        s2 = _make_workflow_step("second")
        wf.add_job(s1)
        wf.add_job(s2)

        assert wf.jobs[0] is s1
        assert wf.jobs[1] is s2


class TestWorkflowGetOutputDataset:
    def test_returns_last_step_output(self, tmp_path):
        params = _make_workflow_parameters(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf.generic_module_parameters = {}
        wf._jobs = []

        mock_output = MagicMock()
        step1 = _make_workflow_step("s1", output=MagicMock())
        step2 = _make_workflow_step("s2", output=mock_output)

        wf._jobs = [step1, step2]
        # Simulate steps having been run
        step1._output_dataset = MagicMock()
        step2._output_dataset = mock_output

        assert wf.get_output_dataset() is mock_output


class TestWorkflowBuildModuleParameters:
    def test_merges_generic_and_custom_parameters(self, tmp_path):
        custom_file = tmp_path / "custom.yaml"
        custom_file.write_text("solver: GLOP\ntimeout: 60\n")

        generic = {"timeout": 30, "log_level": "INFO"}
        result = Workflow.build_module_parameters(generic, custom_file)

        # custom overrides generic
        assert result["timeout"] == 60
        assert result["solver"] == "GLOP"
        # generic key not overridden is preserved
        assert result["log_level"] == "INFO"

    def test_does_not_mutate_generic_parameters(self, tmp_path):
        custom_file = tmp_path / "custom.yaml"
        custom_file.write_text("key: new_value\n")

        generic = {"key": "original"}
        Workflow.build_module_parameters(generic, custom_file)

        assert generic["key"] == "original"

    def test_empty_custom_returns_copy_of_generic(self, tmp_path):
        custom_file = tmp_path / "custom.yaml"
        custom_file.write_text("{}\n")

        generic = {"a": 1, "b": 2}
        result = Workflow.build_module_parameters(generic, custom_file)

        assert result == generic
        assert result is not generic


class TestWorkflowExecute:
    def _make_mock_output(self):
        """Create a mock AbstractModuleOutput with an empty change_sets list."""
        mock_output = MagicMock()
        mock_output.change_sets = []
        return mock_output

    def test_execute_runs_all_steps_in_order(self, tmp_path):
        params = _make_workflow_parameters(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf.generic_module_parameters = {}
        wf._jobs = []
        wf.workflow_path = Path()

        call_order = []

        output1 = self._make_mock_output()
        output2 = self._make_mock_output()

        def run1(ds):
            call_order.append("step1")
            step1._output_dataset = output1

        def run2(ds):
            call_order.append("step2")
            step2._output_dataset = output2

        step1 = _make_workflow_step("step1")
        step1.module.run = MagicMock(side_effect=lambda ds, params: output1)
        step1.run = run1

        step2 = _make_workflow_step("step2")
        step2.module.run = MagicMock(side_effect=lambda ds, params: output2)
        step2.run = run2

        wf._jobs = [step1, step2]

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

            wf.execute()

        assert call_order == ["step1", "step2"]

    def test_execute_raises_if_step_produces_no_output(self, tmp_path):
        params = _make_workflow_parameters(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf.generic_module_parameters = {}
        wf._jobs = []
        wf.workflow_path = Path()

        step = _make_workflow_step("bad_step", output=None)
        # job.run will set _output_dataset = None (the default)
        wf._jobs = [step]

        with (
            patch("atlas.io_utils.atlas_dataset.AtlasDataset.from_directory", return_value=AtlasDataset()),
            patch("atlas.orchestrator.current_input_state.CurrentInputState") as MockCIS,
        ):
            mock_cis_instance = MagicMock()
            mock_cis_instance.filter_dataset.return_value = AtlasDataset()
            MockCIS.return_value = mock_cis_instance

            with pytest.raises(RuntimeError, match="bad_step"):
                wf.execute()

    def test_execute_applies_change_sets_after_each_step(self, tmp_path):
        params = _make_workflow_parameters(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = params
        wf.generic_module_parameters = {}
        wf._jobs = []
        wf.workflow_path = Path()

        mock_change_set = MagicMock()
        output = self._make_mock_output()
        output.change_sets = [mock_change_set]

        step = _make_workflow_step("step1")
        step._output_dataset = output
        step.run = lambda ds: None  # run is a no-op; _output_dataset is pre-set

        wf._jobs = [step]

        with (
            patch("atlas.orchestrator.handler.cis_handler.CISHandler.apply") as mock_apply,
            patch("atlas.orchestrator.current_input_state.CurrentInputState.from_directory") as MockFromDir,
            patch.object(AtlasDataset, "to_directory"),
        ):
            mock_cis_instance = MagicMock()
            mock_cis_instance.filter_dataset.return_value = AtlasDataset()
            mock_cis_instance.data = AtlasDataset()
            MockFromDir.return_value = mock_cis_instance

            wf.execute()

        # Default rollback_on_job_failure is True
        mock_apply.assert_called_once_with([mock_change_set], mock_cis_instance, rollback_on_error=True)


class TestWorkflowFromFile:
    def test_from_file_raises_if_steps_reference_nonexistent_params(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        config = tmp_path / "workflow.yaml"
        config.write_text(
            f"name: wf\n"
            f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"steps:\n"
            f"  - module: PortfolioOptimisation\n"
            f"    parameters_path: /nonexistent/path/params.yaml\n"
        )

        # build_steps will try to open the parameters file -- should raise
        with pytest.raises(Exception):
            Workflow.from_file(config)


class TestWorkflowRepresentation:
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

        config = tmp_path / "workflow.yaml"
        config.write_text(
            f"name: test_workflow\n"
            f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"steps:\n"
            f"  - module: MarketClearing\n"
            f"    parameters_path: {params_file}\n"
        )

        workflow = Workflow.from_file(config)
        result = repr(workflow)
        assert "Workflow 'test_workflow'" in result
        assert "1 step" in result


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
            "path_from_orchestrator: true\n"
            "steps: []\n"
        )

        workflow = Workflow.from_file(config)

        with (
            patch("atlas.orchestrator.current_input_state.CurrentInputState.from_directory") as mock_from_dir,
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
            f"path_from_orchestrator: false\n"
            f"steps: []\n"
        )

        workflow = Workflow.from_file(config)

        with (
            patch("atlas.orchestrator.current_input_state.CurrentInputState.from_directory") as mock_from_dir,
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
            f"path_from_orchestrator: true\n"
            f"output_dir: results\n"
            f"steps:\n"
            f"  - module: MarketClearing\n"
            f"    parameters_path: {params_file}\n"
        )

        workflow = Workflow.from_file(config)
        step = workflow.jobs[0]

        assert step.parameters.output.output_dir == tmp_path / "results" / "MarketClearing"

    def test_generic_parameters_loaded_relative_to_workflow(self, tmp_path):
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        generic_params = tmp_path / "generic.yaml"
        generic_params.write_text("solver_name: XPRESS\n")

        config = tmp_path / "workflow.yaml"
        config.write_text(
            f"name: test_workflow\n"
            f"dataset_path: {dataset_dir}\n"
            f"output_dataset_path: {output_dir}\n"
            f"path_from_orchestrator: true\n"
            f"parameters_path: generic.yaml\n"
            f"steps: []\n"
        )

        workflow = Workflow.from_file(config)

        assert workflow.generic_module_parameters.get("solver_name") == "XPRESS"
