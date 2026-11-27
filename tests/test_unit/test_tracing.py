"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas.tracing import (
    ProcessPoolExecutor,
    RunStore,
    StepRecord,
    _ContextualWorker,
    _step_context,
    get_log_context,
    run_record_of,
    step,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _disabled_store() -> RunStore:
    return RunStore(enabled=False)


# ---------------------------------------------------------------------------
# @step — standalone function
# ---------------------------------------------------------------------------


class TestStepOnFunction:
    def test_returns_value(self):
        @step
        def compute():
            return 42

        with patch("atlas.tracing._run_store", _disabled_store()):
            assert compute() == 42

    def test_run_record_on_success(self):
        @step
        def noop():
            pass

        with patch("atlas.tracing._run_store", _disabled_store()):
            noop()

        assert isinstance(noop.run_record, StepRecord)
        assert noop.run_record.status == "success"
        assert noop.run_record.duration_seconds is not None

    def test_run_record_on_failure(self):
        @step
        def boom():
            raise ValueError("oops")

        with patch("atlas.tracing._run_store", _disabled_store()):
            with pytest.raises(ValueError):
                boom()

        assert boom.run_record.status == "failed"
        assert isinstance(boom.run_record.error, ValueError)

    def test_custom_name(self):
        @step(name="my-step")
        def something():
            pass

        with patch("atlas.tracing._run_store", _disabled_store()):
            something()

        assert something.run_record.name == "my-step"

    def test_callable_name(self):
        @step(name=lambda x: f"step-{x}")
        def work(x):
            pass

        with patch("atlas.tracing._run_store", _disabled_store()):
            work("abc")

        assert work.run_record.name == "step-abc"

    def test_context_reset_after_call(self):
        @step
        def f():
            pass

        assert _step_context.get() is None
        with patch("atlas.tracing._run_store", _disabled_store()):
            f()
        assert _step_context.get() is None

    def test_context_reset_after_exception(self):
        @step
        def f():
            raise ValueError

        with patch("atlas.tracing._run_store", _disabled_store()):
            with pytest.raises(ValueError):
                f()

        assert _step_context.get() is None


# ---------------------------------------------------------------------------
# @step — method on class
# ---------------------------------------------------------------------------


class TestStepOnMethod:
    def test_run_record_stored_on_instance(self):
        class Worker:
            @step(name="worker-step")
            def run(self):
                pass

        w = Worker()
        with patch("atlas.tracing._run_store", _disabled_store()):
            w.run()

        assert isinstance(w.run_record, StepRecord)
        assert w.run_record.name == "worker-step"

    def test_two_instances_have_independent_records(self):
        class Worker:
            @step(name="w")
            def run(self):
                pass

        a, b = Worker(), Worker()
        with patch("atlas.tracing._run_store", _disabled_store()):
            a.run()
            b.run()

        assert a.run_record.run_id != b.run_record.run_id

    def test_callable_name_receives_self(self):
        class Worker:
            def __init__(self, name):
                self.name = name

            @step(name=lambda self: f"step-{self.name}")
            def run(self):
                pass

        w = Worker("alpha")
        with patch("atlas.tracing._run_store", _disabled_store()):
            w.run()

        assert w.run_record.name == "step-alpha"


# ---------------------------------------------------------------------------
# Nesting — child steps
# ---------------------------------------------------------------------------


class TestNestedSteps:
    def test_child_registered_in_parent_children(self):
        @step
        def inner():
            pass

        @step
        def outer():
            inner()

        with patch("atlas.tracing._run_store", _disabled_store()):
            outer()

        assert len(outer.run_record.children) == 1
        assert outer.run_record.children[0].name == "inner"

    def test_child_inherits_parent_run_id(self):
        @step
        def inner():
            pass

        @step
        def outer():
            inner()

        with patch("atlas.tracing._run_store", _disabled_store()):
            outer()

        assert inner.run_record.run_id == outer.run_record.run_id

    def test_grandchild_nesting(self):
        @step
        def leaf():
            pass

        @step
        def mid():
            leaf()

        @step
        def root():
            mid()

        with patch("atlas.tracing._run_store", _disabled_store()):
            root()

        assert len(root.run_record.children) == 1
        assert len(root.run_record.children[0].children) == 1
        assert root.run_record.children[0].children[0].name == "leaf"
        run_id = root.run_record.run_id
        assert mid.run_record.run_id == run_id
        assert leaf.run_record.run_id == run_id

    def test_context_restored_to_parent_after_child(self):
        captured = {}

        @step
        def inner():
            pass

        @step
        def outer():
            inner()
            captured["after_inner"] = _step_context.get().name

        with patch("atlas.tracing._run_store", _disabled_store()):
            outer()

        assert captured["after_inner"] == "outer"

    def test_to_dict_includes_children(self):
        @step
        def inner():
            pass

        @step
        def outer():
            inner()

        with patch("atlas.tracing._run_store", _disabled_store()):
            outer()

        d = outer.run_record.to_dict()
        assert "children" in d
        assert len(d["children"]) == 1
        assert d["children"][0]["name"] == "inner"

    def test_standalone_step_has_own_run_id(self):
        @step
        def standalone():
            pass

        with patch("atlas.tracing._run_store", _disabled_store()):
            standalone()

        assert standalone.run_record.run_id is not None
        assert _step_context.get() is None

    def test_store_called_once_for_root_only(self):
        mock_store = MagicMock()
        mock_store.open_log.return_value = None

        @step
        def inner():
            pass

        @step
        def outer():
            inner()

        with patch("atlas.tracing._run_store", mock_store):
            outer()

        assert mock_store.save.call_count == 1


# ---------------------------------------------------------------------------
# flow and task are aliases of step
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Callable metadata
# ---------------------------------------------------------------------------


class TestCallableMetadata:
    def test_callable_metadata_on_function(self):
        @step(name="t", metadata=lambda x, y: {"sum": x + y})
        def add(x, y):
            return x + y

        with patch("atlas.tracing._run_store", _disabled_store()):
            add(2, 3)

        assert add.run_record.metadata == {"sum": 5}

    def test_static_metadata(self):
        @step(metadata={"version": "1.0"})
        def fn():
            pass

        with patch("atlas.tracing._run_store", _disabled_store()):
            fn()

        assert fn.run_record.metadata == {"version": "1.0"}

    def test_callable_metadata_on_method(self):
        class Worker:
            def __init__(self, label):
                self.label = label

            @step(name="w", metadata=lambda self: {"label": self.label})
            def run(self):
                pass

        w = Worker("prod")
        with patch("atlas.tracing._run_store", _disabled_store()):
            w.run()

        assert w.run_record.metadata == {"label": "prod"}


# ---------------------------------------------------------------------------
# _ContextualWorker — run_id propagation in worker processes
# ---------------------------------------------------------------------------


class TestContextualWorker:
    def test_installs_stub_step_record(self):
        captured = {}

        def probe():
            record = _step_context.get()
            captured["run_id"] = record.run_id if record else None
            captured["name"] = record.name if record else None

        worker = _ContextualWorker(probe, {"step": "my-step", "run_id": "abc123"})
        worker()

        assert captured["run_id"] == "abc123"
        assert captured["name"] == "my-step"

    def test_context_reset_after_worker(self):
        worker = _ContextualWorker(lambda: None, {"step": "s", "run_id": "x"})
        assert _step_context.get() is None
        worker()
        assert _step_context.get() is None

    def test_no_stub_when_context_missing(self):
        captured = {}

        def probe():
            captured["record"] = _step_context.get()

        worker = _ContextualWorker(probe, {})
        worker()
        assert captured["record"] is None

    def test_step_inside_worker_inherits_parent_run_id(self):
        captured = {}

        @step
        def inner():
            pass

        def run_task():
            with patch("atlas.tracing._run_store", _disabled_store()):
                inner()
            captured["run_id"] = inner.run_record.run_id

        worker = _ContextualWorker(run_task, {"step": "parent", "run_id": "parentid"})
        worker()

        assert captured["run_id"] == "parentid"


# ---------------------------------------------------------------------------
# ProcessPoolExecutor — context propagation across processes
# ---------------------------------------------------------------------------


def _worker_get_run_id():
    record = _step_context.get()
    return record.run_id if record else None


class TestProcessPoolExecutor:
    def test_run_id_propagated_to_worker(self):
        @step(name="test-step")
        def pipeline():
            with ProcessPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_worker_get_run_id)
                return future.result(), _step_context.get().run_id

        with patch("atlas.tracing._run_store", _disabled_store()):
            worker_id, parent_id = pipeline()

        assert worker_id == parent_id

    def test_no_wrapper_when_no_step_context(self):
        with ProcessPoolExecutor(max_workers=1) as executor:
            result = executor.submit(_worker_get_run_id).result()

        assert result is None


# ---------------------------------------------------------------------------
# RunStore — persistence
# ---------------------------------------------------------------------------


class TestRunStore:
    def test_save_writes_json(self):
        import json

        import pendulum

        with tempfile.TemporaryDirectory() as tmpdir:
            store = RunStore(enabled=True, dir=Path(tmpdir), log=False)
            record = StepRecord(name="test-step")
            record.started_at = pendulum.now()
            path = store.save(record)

            assert path is not None
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["name"] == "test-step"
            assert "children" in data

    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("RUN_RECORD_ENABLED", raising=False)
        assert RunStore(_env_file=None).enabled is False

    def test_open_log_failure_marks_failed_and_resets_context(self):
        store = MagicMock()
        store.open_log.side_effect = OSError("disk full")

        @step(name="root")
        def root():
            pass

        with patch("atlas.tracing._run_store", store), pytest.raises(OSError, match="disk full"):
            root()

        assert root.run_record.status == "failed"
        assert _step_context.get() is None
        store.close_log.assert_called_once_with(None)
        store.save.assert_called_once_with(root.run_record)

    def test_save_disabled_returns_none(self):
        store = RunStore(enabled=False)
        record = StepRecord(name="noop")
        assert store.save(record) is None

    def test_open_close_log_disabled_returns_none(self):
        import pendulum

        store = RunStore(enabled=False)
        record = StepRecord(name="noop")
        record.started_at = pendulum.now()
        sink_id = store.open_log(record)
        assert sink_id is None
        store.close_log(sink_id)

    def test_open_close_log_creates_file(self):
        import pendulum

        with tempfile.TemporaryDirectory() as tmpdir:
            store = RunStore(enabled=True, dir=Path(tmpdir), log=True)
            record = StepRecord(name="log-step")
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
    def test_empty_outside_step(self):
        assert get_log_context() == {}

    def test_contains_step_and_run_id_inside_step(self):
        @step(name="ctx-step")
        def f():
            return get_log_context()

        with patch("atlas.tracing._run_store", _disabled_store()):
            ctx = f()

        assert ctx["step"] == "ctx-step"
        assert "run_id" in ctx

    def test_child_step_path_includes_ancestors(self):
        captured = {}

        @step(name="child")
        def inner():
            captured["ctx"] = get_log_context()

        @step(name="root")
        def outer():
            inner()

        with patch("atlas.tracing._run_store", _disabled_store()):
            outer()

        assert captured["ctx"]["step"] == "root | child"

    def test_grandchild_path_includes_full_ancestry(self):
        captured = {}

        @step(name="leaf")
        def leaf():
            captured["ctx"] = get_log_context()

        @step(name="mid")
        def mid():
            leaf()

        @step(name="root")
        def root():
            mid()

        with patch("atlas.tracing._run_store", _disabled_store()):
            root()

        assert captured["ctx"]["step"] == "root | mid | leaf"

    def test_path_reset_after_child_returns(self):
        captured = {}

        @step(name="child")
        def inner():
            pass

        @step(name="root")
        def outer():
            inner()
            captured["ctx"] = get_log_context()

        with patch("atlas.tracing._run_store", _disabled_store()):
            outer()

        assert captured["ctx"]["step"] == "root"


def test_run_record_of_returns_the_record_of_the_last_run():
    @step
    def computes():
        return 42

    assert run_record_of(computes) is None
    computes()
    record = run_record_of(computes)
    assert record is not None
    assert record.status == "success"
