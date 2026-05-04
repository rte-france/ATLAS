"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for WorkflowJob, Step, and ModuleRegistry.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atlas.io_utils.atlas_dataset import AtlasDataset
from atlas.modules.market_clearing.module import MarketClearingModule
from atlas.orchestrator.module_registry import ModuleRegistry
from atlas.orchestrator.workflow.job import WorkflowJob
from atlas.orchestrator.workflow.parameters import Step
from tests.test_unit.test_orchestrator.orchestrator_factory import MockModuleBuilder


class TestStep:
    @pytest.fixture
    def params_file(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("export_result: false\n")
        return params_file

    def test_step_coerces_string_module(self, tmp_path, params_file):
        step = Step(module="PortfolioOptimisation", parameters_path=params_file)
        assert step.module == ModuleRegistry.PortfolioOptimisation

    def test_step_default_name_is_module_name(self, tmp_path, params_file):
        step = Step(module="PortfolioOptimisation", parameters_path=params_file)
        assert step.name == "PortfolioOptimisation"

    def test_step_custom_name_is_preserved(self, tmp_path, params_file):
        step = Step(name="my_step", module="PortfolioOptimisation", parameters_path=params_file)
        assert step.name == "my_step"

    def test_step_invalid_module_raises(self, tmp_path, params_file):
        with pytest.raises(Exception):
            Step(module="DoesNotExist", parameters_path=params_file)

    def test_step_parameters_path_is_path_object(self, tmp_path, params_file):
        step = Step(module="PortfolioOptimisation", parameters_path=str(params_file))
        assert isinstance(step.parameters_path, Path)


class TestWorkflowJobInit:
    @pytest.fixture(autouse=True)
    def set_up_mock_module(self):
        self.mock_instance = MockModuleBuilder().build()
        self.mock_class = MagicMock(return_value=self.mock_instance)

    def test_init_sets_name(self):
        ws = WorkflowJob("my_step", self.mock_class, {})
        assert ws.name == "my_step"

    def test_init_instantiates_module(self):
        ws = WorkflowJob("step", self.mock_class, {})
        self.mock_class.assert_called_once()
        assert ws.module is self.mock_instance

    def test_output_dataset_is_none_before_run(self):
        ws = WorkflowJob("step", self.mock_class, {})
        assert ws.output_dataset is None
        assert ws.get_output_dataset() is None


class TestWorkflowJobRun:
    @pytest.fixture
    def atlas_dataset(self):
        return AtlasDataset()

    @pytest.fixture(autouse=True)
    def set_up_module_and_job(self):
        self.mock_output = MagicMock()
        self.mock_instance = MockModuleBuilder().with_output(self.mock_output).build()
        self.mock_class = MagicMock(return_value=self.mock_instance)
        self.job = WorkflowJob("job", self.mock_class, {})

    def test_run_calls_module_run(self, atlas_dataset):
        job = WorkflowJob("job", self.mock_class, {"param": 1})
        job.run(atlas_dataset)
        self.mock_instance.run.assert_called_once_with(atlas_dataset, job.parameters)

    def test_run_stores_output_dataset(self, atlas_dataset):
        self.job.run(atlas_dataset)
        assert self.job.output_dataset is self.mock_output
        assert self.job.get_output_dataset() is self.mock_output

    def test_run_with_none_output_stores_none(self, atlas_dataset):
        mock_instance = MockModuleBuilder().with_output(None).build()
        mock_class = MagicMock(return_value=mock_instance)
        job = WorkflowJob("job", mock_class, {})
        job.run(atlas_dataset)
        assert job.output_dataset is None

    def test_run_overwrites_previous_output(self, atlas_dataset):
        first_output = MagicMock(name="first")
        second_output = MagicMock(name="second")
        self.mock_instance.run.side_effect = [first_output, second_output]

        job = WorkflowJob("job", self.mock_class, {})
        job.run(atlas_dataset)
        assert job.output_dataset is first_output

        job.run(atlas_dataset)
        assert job.output_dataset is second_output

    def test_run_propagates_module_exception(self, atlas_dataset):
        self.mock_instance.run.side_effect = RuntimeError("module crashed")

        job = WorkflowJob("job", self.mock_class, {})
        with pytest.raises(RuntimeError, match="module crashed"):
            job.run(atlas_dataset)

    def test_output_dataset_property_and_get_method_are_consistent(self, atlas_dataset):
        job = WorkflowJob("job", self.mock_class, {})
        job.run(atlas_dataset)

        assert job.output_dataset is job.get_output_dataset()


class TestWorkflowJobRepresentation:
    @pytest.fixture
    def mc_params(self):
        return {
            "temporal": {
                "start_date": "2028-09-27 00:00:00",
                "end_date": "2028-09-28 00:00:00",
                "execution_date": "2028-09-26 12:00:00",
            }
        }

    def test_repr_before_execution(self, mc_params):
        job = WorkflowJob("TestJob", MarketClearingModule, mc_params)
        result = repr(job)
        assert "WorkflowStep(" in result
        assert "name='TestJob'" in result
        assert "executed=False" in result

    def test_repr_after_execution(self, mc_params):
        job = WorkflowJob("TestJob", MarketClearingModule, mc_params)
        job._output_dataset = MagicMock()
        result = repr(job)
        assert "executed=True" in result
