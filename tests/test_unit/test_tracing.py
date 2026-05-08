"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas.tracing import (
    FlowRecord,
    ProcessPoolExecutor,
    RunStore,
    TaskRecord,
    _ContextualWorker,
    _flow_context,
    flow,
    get_log_context,
    task,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _disabled_store():
    """RunStore with persistence disabled — no files written during tests."""
    return RunStore(enabled=False)


# ---------------------------------------------------------------------------
# @task — standalone
# ---------------------------------------------------------------------------


class TestTaskDecorator:
    def test_returns_value(self):
        @task
        def add(a, b):
            return a + b

        assert add(2, 3) == 5

    def test_run_record_on_success(self):
        @task
        def noop():
            pass

        noop()
        assert isinstance(noop.run_record, TaskRecord)
        assert noop.run_record.status == "success"
        assert noop.run_record.duration_seconds is not None

    def test_run_record_on_failure(self):
        @task
        def boom():
            raise ValueError("oops")

        with pytest.raises(ValueError):
            boom()

        assert boom.run_record.status == "failed"
        assert isinstance(boom.run_record.error, ValueError)

    def test_custom_name(self):
        @task(name="my-task")
        def something():
            pass

        something()
        assert something.run_record.name == "my-task"

    def test_callable_name(self):
        @task(name=lambda x: f"task-{x}")
        def work(x):
            pass

        work("abc")
        assert work.run_record.name == "task-abc"

    def test_task_inherits_flow_run_id(self):
        @task
        def inner():
            pass

        @flow(name="parent-flow")
        def parent():
            inner()

        with patch("atlas.tracing._run_store", _disabled_store()):
            parent()

        assert inner.run_record.run_id == parent.run_record.run_id

    def test_task_appended_to_flow_tasks(self):
        @task
        def step():
            pass

        @flow(name="pipe")
        def pipeline():
            step()
            step()

        with patch("atlas.tracing._run_store", _disabled_store()):
            pipeline()

        assert len(parent_record(pipeline).tasks) == 2

    def test_task_outside_flow_has_own_run_id(self):
        @task
        def standalone():
            pass

        standalone()
        assert standalone.run_record.run_id is not None
        assert _flow_context.get() is None


# ---------------------------------------------------------------------------
# @flow — standalone function
# ---------------------------------------------------------------------------


class TestFlowOnFunction:
    def test_returns_value(self):
        @flow
        def compute():
            return 42

        with patch("atlas.tracing._run_store", _disabled_store()):
            assert compute() == 42

    def test_run_record_stored_on_function(self):
        @flow
        def pipeline():
            pass

        with patch("atlas.tracing._run_store", _disabled_store()):
            pipeline()

        assert isinstance(pipeline.run_record, FlowRecord)
        assert pipeline.run_record.status == "success"

    def test_run_record_on_failure(self):
        @flow
        def failing():
            raise RuntimeError("fail")

        with patch("atlas.tracing._run_store", _disabled_store()):
            with pytest.raises(RuntimeError):
                failing()

        assert failing.run_record.status == "failed"
        assert isinstance(failing.run_record.error, RuntimeError)

    def test_flow_context_reset_after_call(self):
        @flow
        def f():
            pass

        assert _flow_context.get() is None
        with patch("atlas.tracing._run_store", _disabled_store()):
            f()
        assert _flow_context.get() is None

    def test_flow_context_reset_after_exception(self):
        @flow
        def f():
            raise ValueError

        with patch("atlas.tracing._run_store", _disabled_store()):
            with pytest.raises(ValueError):
                f()

        assert _flow_context.get() is None


# ---------------------------------------------------------------------------
# @flow — method on class
# ---------------------------------------------------------------------------


class TestFlowOnMethod:
    def test_run_record_stored_on_instance(self):
        class Worker:
            @flow(name="worker-flow")
            def run(self):
                pass

        w = Worker()
        with patch("atlas.tracing._run_store", _disabled_store()):
            w.run()

        assert isinstance(w.run_record, FlowRecord)
        assert w.run_record.name == "worker-flow"

    def test_two_instances_have_independent_records(self):
        class Worker:
            @flow(name="w")
            def run(self):
                pass

        a, b = Worker(), Worker()
        store = _disabled_store()
        with patch("atlas.tracing._run_store", store):
            a.run()
            b.run()

        assert a.run_record.run_id != b.run_record.run_id

    def test_callable_name_receives_self(self):
        class Worker:
            def __init__(self, name):
                self.name = name

            @flow(name=lambda self: f"flow-{self.name}")
            def run(self):
                pass

        w = Worker("alpha")
        with patch("atlas.tracing._run_store", _disabled_store()):
            w.run()

        assert w.run_record.name == "flow-alpha"


# ---------------------------------------------------------------------------
# _ContextualWorker — run_id propagation in worker processes
# ---------------------------------------------------------------------------


class TestContextualWorker:
    def test_installs_stub_flow_record(self):
        captured = {}

        def probe():
            record = _flow_context.get()
            captured["run_id"] = record.run_id if record else None
            captured["name"] = record.name if record else None

        worker = _ContextualWorker(probe, {"flow": "my-flow", "run_id": "abc123"})
        worker()

        assert captured["run_id"] == "abc123"
        assert captured["name"] == "my-flow"

    def test_flow_context_reset_after_worker(self):
        worker = _ContextualWorker(lambda: None, {"flow": "f", "run_id": "x"})
        assert _flow_context.get() is None
        worker()
        assert _flow_context.get() is None

    def test_no_stub_when_context_missing(self):
        captured = {}

        def probe():
            captured["record"] = _flow_context.get()

        worker = _ContextualWorker(probe, {})
        worker()
        assert captured["record"] is None

    def test_task_inside_worker_gets_parent_run_id(self):
        captured = {}

        @task
        def inner():
            captured["run_id"] = inner.run_record.run_id if inner.run_record else None

        def run_task():
            inner()
            captured["run_id"] = inner.run_record.run_id

        worker = _ContextualWorker(run_task, {"flow": "parent", "run_id": "parentid"})
        worker()

        assert captured["run_id"] == "parentid"


# ---------------------------------------------------------------------------
# ProcessPoolExecutor — context propagation across processes
# ---------------------------------------------------------------------------


def _worker_get_run_id():
    record = _flow_context.get()
    return record.run_id if record else None


class TestProcessPoolExecutor:
    def test_run_id_propagated_to_worker(self):
        @flow(name="test-flow")
        def pipeline():
            with ProcessPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_worker_get_run_id)
                return future.result(), _flow_context.get().run_id

        with patch("atlas.tracing._run_store", _disabled_store()):
            worker_id, parent_id = pipeline()

        assert worker_id == parent_id

    def test_no_wrapper_when_no_flow_context(self):
        results = []
        with ProcessPoolExecutor(max_workers=1) as executor:
            results.append(executor.submit(_worker_get_run_id).result())

        assert results[0] is None


# ---------------------------------------------------------------------------
# RunStore — persistence
# ---------------------------------------------------------------------------


class TestRunStore:
    def test_save_writes_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RunStore(enabled=True, dir=Path(tmpdir), log=False)
            import pendulum

            record = FlowRecord(name="test-flow")
            record.started_at = pendulum.now()
            path = store.save(record)

            assert path is not None
            assert path.exists()
            data = __import__("json").loads(path.read_text())
            assert data["name"] == "test-flow"

    def test_save_disabled_returns_none(self):
        store = RunStore(enabled=False)
        record = FlowRecord(name="noop")
        assert store.save(record) is None

    def test_open_close_log_disabled_returns_none(self):
        store = RunStore(enabled=False)
        import pendulum

        record = FlowRecord(name="noop")
        record.started_at = pendulum.now()
        sink_id = store.open_log(record)
        assert sink_id is None
        store.close_log(sink_id)  # must not raise

    def test_open_close_log_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = RunStore(enabled=True, dir=Path(tmpdir), log=True)
            import pendulum

            record = FlowRecord(name="log-flow")
            record.started_at = pendulum.now()
            sink_id = store.open_log(record)
            assert sink_id is not None
            store.close_log(sink_id)

            log_files = list(Path(tmpdir).rglob("run.log"))
            assert len(log_files) == 1


# ---------------------------------------------------------------------------
# get_log_context
# ---------------------------------------------------------------------------


class TestGetLogContext:
    def test_empty_outside_flow(self):
        assert get_log_context() == {}

    def test_contains_flow_and_run_id_inside_flow(self):
        @flow(name="ctx-flow")
        def f():
            return get_log_context()

        with patch("atlas.tracing._run_store", _disabled_store()):
            ctx = f()

        assert ctx["flow"] == "ctx-flow"
        assert "run_id" in ctx

    def test_contains_task_inside_task(self):
        captured = {}

        @task(name="my-task")
        def t():
            captured["ctx"] = get_log_context()

        t()
        assert captured["ctx"].get("task") == "my-task"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def parent_record(decorated_flow) -> FlowRecord:
    return decorated_flow.run_record
