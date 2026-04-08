"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for WorkflowJob, Step, and ModuleRegistry.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atlas.abstract_class.abstract_module import AbstractModule
from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.modules.portfolio_optimisation.module import PortfolioOptimisationModule
from atlas.orchestrator.module_registry import ModuleRegistry
from atlas.orchestrator.workflow.job import Step
from atlas.orchestrator.workflow.job import WorkflowJob


def _make_mock_module_class(output=None):
    """Return a (mock_class, mock_instance) pair where instance.run() returns output."""
    mock_instance = MagicMock()
    mock_instance.run.return_value = output
    mock_instance.get_business_model_class_used.return_value = []
    mock_instance.get_filters.return_value = None

    mock_class = MagicMock(return_value=mock_instance)
    return mock_class, mock_instance


@pytest.fixture
def atlas_dataset():
    return AtlasDataset()


class TestModuleRegistry:
    def test_get_known_module_returns_class(self):
        cls = ModuleRegistry.get("PortfolioOptimisation")
        assert cls is PortfolioOptimisationModule

    def test_get_unknown_module_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown module"):
            ModuleRegistry.get("NonExistentModule")

    def test_all_registry_entries_are_abstract_module_subclasses(self):
        for member in ModuleRegistry:
            assert issubclass(member.value, AbstractModule)


class TestStep:
    def test_step_coerces_string_module(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("export_result: false\n")

        step = Step(module="PortfolioOptimisation", parameters_path=params_file)
        assert step.module == ModuleRegistry.PortfolioOptimisation

    def test_step_default_name_is_module_name(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("export_result: false\n")

        step = Step(module="PortfolioOptimisation", parameters_path=params_file)
        assert step.name == "PortfolioOptimisation"

    def test_step_custom_name_is_preserved(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("export_result: false\n")

        step = Step(name="my_step", module="PortfolioOptimisation", parameters_path=params_file)
        assert step.name == "my_step"

    def test_step_invalid_module_raises(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("export_result: false\n")

        with pytest.raises(Exception):
            Step(module="DoesNotExist", parameters_path=params_file)

    def test_step_parameters_path_is_path_object(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("export_result: false\n")

        step = Step(module="PortfolioOptimisation", parameters_path=str(params_file))
        assert isinstance(step.parameters_path, Path)


class TestWorkflowJobInit:
    def test_init_sets_name(self):
        mock_class, _ = _make_mock_module_class()
        ws = WorkflowJob("my_step", mock_class, {})
        assert ws.name == "my_step"

    def test_init_instantiates_module(self):
        mock_class, mock_instance = _make_mock_module_class()
        ws = WorkflowJob("step", mock_class, {})
        mock_class.assert_called_once()
        assert ws.module is mock_instance

    def test_output_dataset_is_none_before_run(self):
        mock_class, _ = _make_mock_module_class()
        ws = WorkflowJob("step", mock_class, {})
        assert ws.output_dataset is None
        assert ws.get_output_dataset() is None


class TestWorkflowJobRun:
    def test_run_calls_module_run(self, atlas_dataset):
        mock_output = MagicMock()
        mock_class, mock_instance = _make_mock_module_class(output=mock_output)

        ws = WorkflowJob("step", mock_class, {"param": 1})
        ws.run(atlas_dataset)

        mock_instance.run.assert_called_once_with(atlas_dataset, ws.parameters)

    def test_run_stores_output_dataset(self, atlas_dataset):
        mock_output = MagicMock()
        mock_class, _ = _make_mock_module_class(output=mock_output)

        ws = WorkflowJob("step", mock_class, {})
        ws.run(atlas_dataset)

        assert ws.output_dataset is mock_output
        assert ws.get_output_dataset() is mock_output

    def test_run_with_none_output_stores_none(self, atlas_dataset):
        mock_class, _ = _make_mock_module_class(output=None)
        ws = WorkflowJob("step", mock_class, {})
        ws.run(atlas_dataset)
        assert ws.output_dataset is None

    def test_run_overwrites_previous_output(self, atlas_dataset):
        first_output = MagicMock(name="first")
        second_output = MagicMock(name="second")

        mock_class, mock_instance = _make_mock_module_class()
        mock_instance.run.side_effect = [first_output, second_output]

        ws = WorkflowJob("step", mock_class, {})
        ws.run(atlas_dataset)
        assert ws.output_dataset is first_output

        ws.run(atlas_dataset)
        assert ws.output_dataset is second_output

    def test_run_propagates_module_exception(self, atlas_dataset):
        mock_class, mock_instance = _make_mock_module_class()
        mock_instance.run.side_effect = RuntimeError("module crashed")

        ws = WorkflowJob("step", mock_class, {})
        with pytest.raises(RuntimeError, match="module crashed"):
            ws.run(atlas_dataset)

    def test_output_dataset_property_and_get_method_are_consistent(self, atlas_dataset):
        mock_output = MagicMock()
        mock_class, _ = _make_mock_module_class(output=mock_output)

        ws = WorkflowJob("step", mock_class, {})
        ws.run(atlas_dataset)

        assert ws.output_dataset is ws.get_output_dataset()


class TestWorkflowJobRepresentation:
    def _make_mc_params(self):
        return {
            "temporal": {
                "start_date": "2028-09-27 00:00:00",
                "end_date": "2028-09-28 00:00:00",
                "execution_date": "2028-09-26 12:00:00",
            }
        }

    def test_repr_before_execution(self):
        step = WorkflowJob("TestStep", MarketClearingModule, self._make_mc_params())
        result = repr(step)
        assert "WorkflowStep(" in result
        assert "name='TestStep'" in result
        assert "executed=False" in result

    def test_repr_after_execution(self):
        step = WorkflowJob("TestStep", MarketClearingModule, self._make_mc_params())
        step._output_dataset = MagicMock()
        result = repr(step)
        assert "executed=True" in result
