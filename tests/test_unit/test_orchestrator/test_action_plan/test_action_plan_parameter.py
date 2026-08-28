"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from pathlib import Path

import pendulum
import pytest
from pendulum import Duration
from pydantic_extra_types.pendulum_dt import DateTime

from atlas.custom_errors import DataQualityWarning
from atlas.orchestrator.workflow.workflow import Workflow
from atlas.orchestrator.actionplan.parameters import Task, TaskWorkflow, TaskModule
from atlas.orchestrator.module_registry import ModuleRegistry
from tests.test_unit.test_orchestrator.orchestrator_factory import OrchestratorConfigBuilder

class TestTask:
    @pytest.fixture
    def params_file(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text("export_result: false\n")
        return params_file

    @pytest.fixture
    def empty_workflow(self, tmp_path):
        return OrchestratorConfigBuilder().build_workflow(tmp_path)

    @staticmethod
    def build_task_module(
            name: str | None = None,
            module: ModuleRegistry | None = None,
            parameters_path: Path | None = None,
            priority: int = 1,
            from_: DateTime | None = None,
            until: DateTime | None = None,
            frequency: Duration | None = None,
            offset_start_date: Duration | None = None,
            offset_end_date: Duration | None = None):
        return TaskModule(
            name=name,
            module=module,
            parameters_path=parameters_path,
            priority=priority,
            from_=from_ or DateTime(2026, 1, 1),
            until=until or DateTime(2026, 1, 1),
            frequency=frequency or Duration(days=1),
            offset_start_date=offset_start_date or Duration(days=1),
            offset_end_date=offset_end_date or Duration(days=2),
        )

    @staticmethod
    def build_task_workflow(
            name: str | None = None,
            workflow: Workflow | Path | None = None,
            priority: int = 1,
            from_: DateTime | None = None,
            until: DateTime | None = None,
            frequency: Duration | None = None,
            offset_start_date: Duration | None = None,
            offset_end_date: Duration | None = None):
        return TaskWorkflow(
            name=name,
            workflow=workflow,
            priority=priority,
            from_=from_ or DateTime(2026, 1, 1),
            until=until or DateTime(2026, 1, 1),
            frequency=frequency or Duration(days=1),
            offset_start_date=offset_start_date or Duration(days=1),
            offset_end_date=offset_end_date or Duration(days=2),
        )

    def test_coerces_string_module(self, tmp_path, params_file):
        task = TestTask.build_task_module(module="PortfolioOptimisation", parameters_path=params_file)
        assert task.module == ModuleRegistry.PortfolioOptimisation

    def test_default_name_is_module_name(self, tmp_path, params_file):
        task = TestTask.build_task_module(module="PortfolioOptimisation", parameters_path=params_file)
        assert task.name == "PortfolioOptimisation"

    def test_custom_name_is_preserved(self, tmp_path, params_file):
        task = TestTask.build_task_module(name="task_name_test", module="PortfolioOptimisation", parameters_path=params_file)
        assert task.name == "task_name_test"

    def test_invalid_module_raises(self, tmp_path, params_file):
        with pytest.raises(Exception):
            TestTask.build_task_module(module="DoesNotExist", parameters_path=params_file)

    def test_invalid_workflow_raise(self, params_file):
        with pytest.raises(Exception):
            TestTask.build_task_workflow(workflow="DoesNotExist")

    def test_parameters_path_is_path_object_module(self, tmp_path, params_file):
        task = TestTask.build_task_module(module="PortfolioOptimisation", parameters_path=str(params_file))
        assert isinstance(task.parameters_path, Path)

    def test_datetime_are_preserved(self, params_file, empty_workflow):
        from_ = pendulum.DateTime(year=1, month=1, day=1)
        until = pendulum.DateTime(year=1, month=1, day=2)

        task = TestTask.build_task_module(from_=from_, until=until, parameters_path=params_file, module="PortfolioOptimisation")
        assert task.from_.replace(tzinfo=None) == from_
        assert task.until.replace(tzinfo=None) == until

        task = TestTask.build_task_workflow(from_=from_, until=until, workflow=empty_workflow)
        assert task.from_.replace(tzinfo=None) == from_
        assert task.until.replace(tzinfo=None) == until

    def test_duration_are_preserved(self, params_file, empty_workflow):
        frequency = pendulum.Duration(years=1, months=1, days=1)
        offset_start_date = pendulum.Duration(years=2, months=2, days=2)
        offset_end_date = pendulum.Duration(years=3, months=3, days=3)

        task = TestTask.build_task_module(frequency=frequency, offset_start_date=offset_start_date, offset_end_date=offset_end_date, parameters_path=params_file, module="PortfolioOptimisation")
        assert task.frequency == frequency
        assert task.offset_start_date == offset_start_date
        assert task.offset_end_date == offset_end_date

        task = TestTask.build_task_workflow(frequency=frequency, offset_start_date=offset_start_date, offset_end_date=offset_end_date, workflow=empty_workflow)
        assert task.frequency == frequency
        assert task.offset_start_date == offset_start_date
        assert task.offset_end_date == offset_end_date

    def test_raise_from_greater_than_until(self, params_file, empty_workflow):
        with pytest.raises(Exception):
            TestTask.build_task_module(
                from_=DateTime(2000, 1, 2),
                until=DateTime(2000, 1, 1),
                parameters_path=params_file,
                module="PortfolioOptimisation")

        with pytest.raises(Exception):
            TestTask.build_task_workflow(
                from_=DateTime(2000, 1, 2),
                until=DateTime(2000, 1, 1),
                parameters_path=params_file,
                workflow=empty_workflow)

    def test_warning_frequency_dont_reach_until(self, params_file, empty_workflow):
        with pytest.warns(DataQualityWarning):
            TestTask.build_task_module(
                frequency=pendulum.Duration(days=10),
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 15),
                parameters_path=params_file,
                module="PortfolioOptimisation")

        with pytest.warns(DataQualityWarning):
            TestTask.build_task_workflow(
                frequency=pendulum.Duration(days=10),
                from_=DateTime(2000, 1, 1),
                until=DateTime(2000, 1, 15),
                workflow=empty_workflow)
