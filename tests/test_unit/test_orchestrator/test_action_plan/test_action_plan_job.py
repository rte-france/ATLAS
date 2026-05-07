"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from unittest.mock import MagicMock

import pytest
from pendulum import DateTime, Duration

from atlas import MarketClearingModule
from atlas.orchestrator.actionplan.job import ActionPlanJob, ModuleTaskIterator, WorkflowTaskIterator
from tests.test_unit.test_orchestrator.orchestrator_factory import MockModuleBuilder, MockModuleParametersBuilder, \
    MockTaskBuilder, ConcreteTaskIterator, MockJobBuilder


class TestTaskIterator:
    @pytest.fixture
    def task_builder_partially_built(self):
        return (MockTaskBuilder().with_from_until_frequency(
            from_=DateTime(2016, 9, 1),
            until=DateTime(2016, 9, 3),
            frequency=Duration(days=1)))


    def test_next_execution_date(self, task_builder_partially_built):
        task = task_builder_partially_built.build()
        task_iterator = ConcreteTaskIterator(task)
        expected_next_execution_date =(
            [DateTime(2016, 9, 1),
            DateTime(2016, 9, 2),
            DateTime(2016, 9, 3)])

        for idx, jobs in enumerate(task_iterator):
            for job in jobs:
                assert job.parameters.temporal.execution_date == expected_next_execution_date[idx]


    def test_next_start_date(self, task_builder_partially_built):
        task = task_builder_partially_built.with_offset_start_date(Duration(days=0, hours=3, minutes=7)).build()
        task_iterator = ConcreteTaskIterator(task)
        expected_next_start_date = (
            [DateTime(2016, 9, 1, 3*1, 7*1),
             DateTime(2016, 9, 1, 3*2, 7*2),
             DateTime(2016, 9, 1, 3*3, 7*3)])

        for idx, jobs in enumerate(task_iterator):
            for job in jobs:
                assert job.parameters.temporal.start_date == expected_next_start_date[idx]


    def test_next_end_date(self, task_builder_partially_built):
        task = task_builder_partially_built.with_offset_end_date(Duration(days=0, hours=5, minutes=11)).build()
        task_iterator = ConcreteTaskIterator(task)
        expected_next_end_date = (
            [DateTime(2016, 9, 1, 5*1, 11*1),
             DateTime(2016, 9, 1, 5*2, 11*2),
             DateTime(2016, 9, 1, 5*3, 11*3)])

        for idx, jobs in enumerate(task_iterator):
            for job in jobs:
                assert job.parameters.temporal.end_date == expected_next_end_date[idx]


    def test_next_execution_date_keep_under_until(self):
        from_ = DateTime(2016, 9, 1)
        until = DateTime(2016, 9, 6)
        frequency = Duration(days=2)
        assert (until - from_).total_seconds() % frequency.total_seconds() != 0

        task = MockTaskBuilder().with_from_until_frequency(from_= from_, until=until, frequency= frequency).build()
        task_iterator = ConcreteTaskIterator(task)
        for idx, jobs in enumerate(task_iterator):
            for job in jobs:
                assert job.parameters.temporal.end_date <= until


    def test_iter_reset_iterator(self, task_builder_partially_built):
        task =task_builder_partially_built.build()
        task_iterator = ConcreteTaskIterator(task)
        itr = task_iterator.__iter__()
        job = next(itr)
        itr = task_iterator.__iter__()
        assert job == next(itr)

    def test_lesser_than_different_execution_date(self):
        task1 = (MockTaskBuilder().with_from_until_frequency(
            from_=DateTime(2016, 1, 1),
            until=DateTime(2020, 1, 1),
            frequency=Duration(years=1))).build()
        task_iterator1 = ConcreteTaskIterator(task1)

        task2 = (MockTaskBuilder().with_from_until_frequency(
            from_=DateTime(2018, 1, 1),
            until=DateTime(2019, 1, 1),
            frequency=Duration(months=1))).build()
        task_iterator2 = ConcreteTaskIterator(task2)

        assert task_iterator1.__lt__(task_iterator2)

    def test_lesser_than_different_priority(self, task_builder_partially_built):
        task1 = task_builder_partially_built.with_priority(1).build()
        task_iterator1 = ConcreteTaskIterator(task1)

        task2 = task_builder_partially_built.with_priority(2).build()
        task_iterator2 = ConcreteTaskIterator(task2)

        assert task_iterator1.__lt__(task_iterator2)

    def test_equal_identical(self, task_builder_partially_built):
        ti1 = ConcreteTaskIterator(task_builder_partially_built.build())
        ti2 = ConcreteTaskIterator(task_builder_partially_built.build())
        assert ti1.__eq__(ti2)

    def test_not_equal_priority_diff(self, task_builder_partially_built):
        ti1 = ConcreteTaskIterator(task_builder_partially_built.with_priority(1).build())
        ti2 = ConcreteTaskIterator(task_builder_partially_built.with_priority(2).build())
        assert not ti1.__eq__(ti2)

    def test_not_equal_execution_date_diff(self, ):
        ti1 = ConcreteTaskIterator(MockTaskBuilder().with_from_until_frequency(
                from_=DateTime(2001, 1, 1),
                until=DateTime(2004, 1, 1),
                frequency=Duration(days=1)).build())
        ti2 = ConcreteTaskIterator(MockTaskBuilder().with_from_until_frequency(
            from_=DateTime(2002, 1, 1),
            until=DateTime(2003, 1, 1),
            frequency=Duration(days=1)).build())
        assert not ti1.__eq__(ti2)

class TestModuleTaskIterator:
    def test_build_current_parameters(self, tmp_path):
        date = DateTime(2000, 1, 1)
        off_set_start = Duration(hours=12)
        off_set_end = Duration(hours=24)

        module = MockModuleBuilder().build()
        parameters = MockModuleParametersBuilder().build()
        task = (MockTaskBuilder()
                .with_from_until_frequency(
                    from_=date,
                    until=date + Duration(days=1),
                    frequency=Duration(days=1))
                .with_priority(1)
                .with_module(module)
                .with_parameters(parameters).build())
        itr = ModuleTaskIterator(task, parameters, tmp_path)
        generated_parameters = itr._build_current_parameters()
        assert generated_parameters.temporal.execution_date == date
        assert generated_parameters.temporal.start_date == date + off_set_start
        assert generated_parameters.temporal.end_date == date + off_set_end
        assert generated_parameters.output.output_dir == tmp_path / date


    def test_build_jobs_has_good_parameters(self, tmp_path):
        # FIXME
        pass

    def test_raise_task_has_no_module(self):
        task = (MockTaskBuilder()
                .with_from_until_frequency(
                    from_=DateTime(2000, 1, 1),
                    until=DateTime(2000, 1, 3),
                    frequency=Duration(days=1))
                .with_priority(1)
                .with_module(None).build())
        with pytest.raises(TypeError):
            ModuleTaskIterator(task)

    def test_iterator_len(self):
        pass #FIXME
        # #test __len__(self)


class WorkflowTaskIterator:
    def test_build_jobs_temporal_parameters(self):
        # test abstract job have good temporal parameter
        # test with one abstract job (workflow with 1 job)
        # test with multiple abstract job (workflow with 3 jobs, and in the expected order)
        pass #FIXME


    def test_raise_task_has_no_workflow(self):
        task = (MockTaskBuilder()
                .with_from_until_frequency(
                    from_=DateTime(2000, 1, 1),
                    until=DateTime(2000, 1, 3),
                    frequency=Duration(days=1))
                .with_priority(1)
                .with_workflow(None).build())
        with pytest.raises(TypeError):
            WorkflowTaskIterator(task)

    def test_iterator_len(self):
        pass #FIXME
        # #test __len__(self)


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
