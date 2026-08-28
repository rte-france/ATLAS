"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import copy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pendulum import DateTime, Duration

from atlas import MarketClearingModule
from atlas.modules.portfolio_optimisation.parameters import PortfolioOptimisationParameters
from atlas.orchestrator.actionplan.job import ActionPlanJob, ModuleTaskJobsGenerator, WorkflowTaskJobsGenerator
from atlas.orchestrator.actionplan.parameters import TaskModule, TaskWorkflow
from atlas.timing import build_datetime
from tests.test_unit.test_orchestrator.orchestrator_factory import ModuleConfigBuilder
from tests.test_unit.test_orchestrator.orchestrator_factory import MockModuleBuilder, MockModuleParametersBuilder, \
    MockTaskBuilder, ConcreteTaskGenerator
from atlas.orchestrator.workflow.workflow import Workflow
from tests.test_unit.test_orchestrator.orchestrator_factory import MockJobBuilder, OrchestratorConfigBuilder

class TestTaskIterator:
    @pytest.fixture
    def task(self, tmp_path):
        return TaskModule(
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=DateTime(2016, 9, 1),
                until=DateTime(2016, 9, 3),
                frequency=Duration(days=1),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        )


    def test_execution_date(self, task):
        task_iterator = ConcreteTaskGenerator(task)
        expected_execution_date =(
            [build_datetime("2016-09-01 00:00:00"),
             build_datetime("2016-09-02 00:00:00"),
             build_datetime("2016-09-03 00:00:00")])

        for index, expected_result in enumerate(expected_execution_date):
            assert task_iterator.execution_date(index+1) == expected_result

    def test_start_date(self, task):
        task.offset_start_date = Duration(days=0, hours=3, minutes=7)
        task_iterator = ConcreteTaskGenerator(task)
        expected_start_date = (
            [build_datetime("2016-09-01 03:07:00"),
            build_datetime("2016-09-02 03:07:00"),
            build_datetime("2016-09-03 03:07:00")])

        for index, expected_result in enumerate(expected_start_date):
            assert task_iterator.start_date(index+1) == expected_result



    def test_next_end_date(self, task):
        task.offset_end_date = Duration(days=0, hours=5, minutes=11)
        task_iterator = ConcreteTaskGenerator(task)
        expected_end_date = (
            [build_datetime("2016-09-01 05:11:00"),
            build_datetime("2016-09-02 05:11:00"),
            build_datetime("2016-09-03 05:11:00")])

        for index, expected_result in enumerate(expected_end_date):
            assert task_iterator.end_date(index+1) == expected_result

    def test_lesser_than_different_execution_date(self, tmp_path):
        task1 = TaskModule(
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=build_datetime("2016-01-01 00:00:00"),
                until=build_datetime("2020-01-01 00:00:00"),
                frequency=Duration(years=1),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        )
        task2 = TaskModule(
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=build_datetime("2018-01-01 00:00:00"),
                until=build_datetime("2019-01-01 00:00:00"),
                frequency=Duration(months=1),
                offset_start_date=Duration(days=1),
                offset_end_date=Duration(days=2),
        )
        task_iterator1 = ConcreteTaskGenerator(task1)
        task_iterator2 = ConcreteTaskGenerator(task2)

        assert task_iterator1.__lt__(task_iterator2)

    def test_lesser_than_different_priority(self, task):
        task1 = copy.copy(task)
        task1.priority = 1
        task_iterator1 = ConcreteTaskGenerator(task1)

        task2 = copy.copy(task)
        task2.priority = 2
        task_iterator2 = ConcreteTaskGenerator(task2)

        assert task_iterator1.__lt__(task_iterator2)

    def test_equal_identical(self, task):
        ti1 = copy.copy(task)
        ti2 = copy.copy(task)
        assert ti1.__eq__(ti2)

    def test_not_equal_priority_diff(self, task):
        task1 = copy.copy(task)
        task1.priority = 1
        task_iterator1 = ConcreteTaskGenerator(task1)

        task2 = copy.copy(task)
        task2.priority = 2
        task_iterator2 = ConcreteTaskGenerator(task2)

        assert not task1.__eq__(task2)

    def test_not_equal_execution_date_diff(self, task):
        task1 = copy.copy(task)
        task1.from_ = build_datetime("2001-01-01 00:00:00")
        task1.until = build_datetime("2004-01-01 00:00:00")
        task1.frequency = Duration(days=1)

        task2 = copy.copy(task)
        task2.from_ = build_datetime("2002-01-01 00:00:00")
        task2.until = build_datetime("2003-01-01 00:00:00")
        task2.frequency = Duration(days=1)

        assert not task1.__eq__(task2)

class TestModuleTaskIterator:
    def test_build_current_parameters(self, tmp_path):
        parameters = MockModuleParametersBuilder().build()
        task = TaskModule(
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=build_datetime("2000-01-01 00:00:00"),
                until=build_datetime("2000-01-02 00:00:00"),
                frequency=Duration(days=1),
                offset_start_date=Duration(hours=12),
                offset_end_date=Duration(hours=24),
        )

        itr = ModuleTaskJobsGenerator(task, parameters, tmp_path)
        generated_parameters = itr._build_parameters(1)
        assert generated_parameters.temporal.execution_date == build_datetime("2000-01-01 00:00:00")
        assert generated_parameters.temporal.start_date == build_datetime("2000-01-01 12:00:00")
        assert generated_parameters.temporal.end_date == build_datetime("2000-01-02 00:00:00")


    def test_build_jobs_has_good_parameters(self, tmp_path):
        parameters_path = ModuleConfigBuilder().build(tmp_path)
        parameters = PortfolioOptimisationParameters.from_file(parameters_path)
        task = TaskModule(
                module="PortfolioOptimisation",
                parameters_path=ModuleConfigBuilder().build(tmp_path),
                priority=1,
                from_=build_datetime("2000-01-01 00:00:00"),
                until=build_datetime("2000-01-02 00:00:00"),
                frequency=Duration(days=1),
                offset_start_date=Duration(hours=12),
                offset_end_date=Duration(hours=24),
        )
        itr = ModuleTaskJobsGenerator(task, parameters, tmp_path)
        job = itr.build_jobs(1)[0]
        generated_parameters = job.parameters
        assert generated_parameters.temporal.execution_date == build_datetime("2000-01-01 00:00:00")
        assert generated_parameters.temporal.start_date == build_datetime("2000-01-01 12:00:00")
        assert generated_parameters.temporal.end_date == build_datetime("2000-01-02 00:00:00")


    def test_raise_task_has_no_module(self):
        task = (MockTaskBuilder()
                .with_from_until_frequency(
                    from_=DateTime(2000, 1, 1),
                    until=DateTime(2000, 1, 3),
                    frequency=Duration(days=1))
                .with_priority(1)
                .with_module_and_parameters(None, None).build())
        with pytest.raises(TypeError):
            ModuleTaskJobsGenerator(task)

    def test_iterator_len(self, tmp_path):
        date = DateTime(2000, 1, 1)
        module = MockModuleBuilder().build()
        parameters = MockModuleParametersBuilder().build()
        partial_task = MockTaskBuilder().with_priority(1).with_module_and_parameters(module, parameters)

        task1 = partial_task.with_from_until_frequency(
                    from_=date,
                    until=date + Duration(days=1),
                    frequency=Duration(days=1)).build()
        itr = ModuleTaskJobsGenerator(task1, parameters, tmp_path)
        assert itr.__len__() == 2

        task2 = partial_task.with_from_until_frequency(
                    from_=date,
                    until=date + Duration(days=9),
                    frequency=Duration(days=1)).build()
        itr = ModuleTaskJobsGenerator(task2, parameters, tmp_path)
        assert itr.__len__() == 10

        task3 = partial_task.with_from_until_frequency(
                    from_=date,
                    until=date + Duration(days=10),
                    frequency=Duration(days=7)).build()
        itr = ModuleTaskJobsGenerator(task3, parameters, tmp_path)
        assert itr.__len__() == 2

        task4 = partial_task.with_from_until_frequency(
                    from_=date,
                    until=date + Duration(days=1),
                    frequency=Duration(days=5)).build()
        itr = ModuleTaskJobsGenerator(task4, parameters, tmp_path)
        assert itr.__len__() == 1


class TestWorkflowTaskIterator:
    def test_build_current_parameters(self, tmp_path):
        parameters = OrchestratorConfigBuilder().build_workflow(tmp_path)
        workflow = Workflow.from_file(parameters)
        task = TaskWorkflow(
                workflow=workflow,
                priority=1,
                from_=build_datetime("2000-01-01 00:00:00"),
                until=build_datetime("2000-01-02 00:00:00"),
                frequency=Duration(days=1),
                offset_start_date=Duration(hours=12),
                offset_end_date=Duration(hours=24),
        )

        itr = WorkflowTaskJobsGenerator(task, workflow.parameters, tmp_path)
        generated_parameters = itr._build_parameters(0)
        assert generated_parameters.context.forced["temporal"]["execution_date"] == build_datetime("2000-01-01 00:00:00")
        assert generated_parameters.context.forced["temporal"]["start_date"] == build_datetime("2000-01-01 12:00:00")
        assert generated_parameters.context.forced["temporal"]["end_date"] == build_datetime("2000-01-02 00:00:00")


    def test_build_jobs_has_good_parameters(self, tmp_path):
        params_file = tmp_path / "params.yaml"
        params_file.write_text(
            "temporal:\n"
            "  start_date: '2028-09-27 00:00:00'\n"
            "  end_date: '2028-09-28 00:00:00'\n"
            "  execution_date: '2028-09-26 12:00:00'\n"
            "solver:\n"
            "  solver_name: GLOP\n"
        )
        config = OrchestratorConfigBuilder().with_name("test_workflow").with_any(
            f"steps:\n"
            f"  - module: MarketClearing\n"
            f"    parameters_path: {params_file}\n"
        ).build(tmp_path)
        workflow = Workflow.from_file(config)
        task = TaskWorkflow(
                workflow=workflow,
                priority=1,
                from_=build_datetime("2000-01-01 00:00:00"),
                until=build_datetime("2000-01-02 00:00:00"),
                frequency=Duration(days=1),
                offset_start_date=Duration(hours=12),
                offset_end_date=Duration(hours=24),
        )

        itr = WorkflowTaskJobsGenerator(task, workflow.parameters, tmp_path)
        job = itr.build_jobs(1)[0]
        generated_parameters = job.parameters
        assert generated_parameters.temporal.execution_date == build_datetime("2000-01-01 00:00:00")
        assert generated_parameters.temporal.start_date == build_datetime("2000-01-01 12:00:00")
        assert generated_parameters.temporal.end_date == build_datetime("2000-01-02 00:00:00")

    def test_iterator_len(self, tmp_path):
        date = DateTime(2000, 1, 1)
        module_parameters = (MockModuleParametersBuilder()
                             .with_execution_date(date + Duration(years=1))
                             .with_start_date(date + Duration(years=2))
                             .with_end_date(date + Duration(years=3))
                             .build())

        conf = OrchestratorConfigBuilder().build_workflow(tmp_path)
        wf = Workflow.__new__(Workflow)
        wf.parameters = Workflow.from_file(conf)
        wf._jobs = [MockJobBuilder().with_module_parameters(module_parameters).build()]

        partial_task = MockTaskBuilder().with_priority(1).with_workflow(wf)

        task1 = partial_task.with_from_until_frequency(
                    from_=date,
                    until=date + Duration(days=1),
                    frequency=Duration(days=1)).build()
        itr = WorkflowTaskJobsGenerator(task1, wf.parameters, tmp_path)
        assert itr.__len__() == 2

        task2 = partial_task.with_from_until_frequency(
                    from_=date,
                    until=date + Duration(days=9),
                    frequency=Duration(days=1)).build()
        itr = WorkflowTaskJobsGenerator(task2, wf.parameters, tmp_path)
        assert itr.__len__() == 10

        task3 = partial_task.with_from_until_frequency(
                    from_=date,
                    until=date + Duration(days=10),
                    frequency=Duration(days=7)).build()
        itr = WorkflowTaskJobsGenerator(task3, wf.parameters, tmp_path)
        assert itr.__len__() == 2

        task4 = partial_task.with_from_until_frequency(
                    from_=date,
                    until=date + Duration(days=2),
                    frequency=Duration(days=7)).build()
        itr = WorkflowTaskJobsGenerator(task4, wf.parameters, tmp_path)
        assert itr.__len__() == 1

class TestTestActionPlanJobRepresentation:
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
        job = ActionPlanJob("TestJob", MarketClearingModule, mc_params)
        result = repr(job)
        assert "ActionPlanStep(" in result
        assert "name='TestJob'" in result
        assert "executed=False" in result

    def test_repr_after_execution(self, mc_params):
        job = ActionPlanJob("TestJob", MarketClearingModule, mc_params)
        job._output_dataset = MagicMock()
        result = repr(job)
        assert "executed=True" in result
