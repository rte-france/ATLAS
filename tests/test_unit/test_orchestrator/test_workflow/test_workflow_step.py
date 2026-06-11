"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for WorkflowJob, Step, and ModuleRegistry.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atlas.core.orchestrator.module_registry import ModuleRegistry
from atlas.core.orchestrator.workflow.job import WorkflowJob
from atlas.core.orchestrator.workflow.parameters import Step
from atlas.modules.market_clearing.module import MarketClearingModule


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
