"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import concurrent.futures
import functools
import json
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Literal, TypeVar

import pendulum
from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

F = TypeVar("F", bound=Callable[..., Any])

_flow_context: ContextVar[FlowRecord | None] = ContextVar("_flow_context", default=None)
_task_context: ContextVar[str | None] = ContextVar("_task_context", default=None)


def get_log_context() -> dict[str, str]:
    """Return the current flow/task/run_id context as a plain dict.

    Useful for advanced cases where you need to propagate context manually.
    For ``ProcessPoolExecutor``, prefer importing it from ``atlas.tracing`` directly —
    it propagates context automatically without any changes to worker functions.
    """
    ctx: dict[str, str] = {}
    flow_record = _flow_context.get()
    if flow_record is not None:
        ctx["flow"] = flow_record.name
        ctx["run_id"] = flow_record.run_id
    task_name = _task_context.get()
    if task_name is not None:
        ctx["task"] = task_name
    return ctx


class _ContextualWorker:
    """Picklable wrapper that restores the log context in a child process.

    Propagates the parent's flow/task names and ``run_id`` so that ``@task``
    calls inside the worker emit logs tagged with the parent flow's run_id.
    A stub :class:`FlowRecord` is installed in ``_flow_context`` so nested
    tasks see the parent's run_id, but their :class:`TaskRecord` objects are
    **not** aggregated back into the parent (mutations don't cross process
    boundaries). For full task aggregation, run inside the parent process.
    """

    __slots__ = ("fn", "log_ctx")

    def __init__(self, fn: Callable, log_ctx: dict[str, str]) -> None:
        self.fn = fn
        self.log_ctx = log_ctx

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        flow_token = None
        flow_name = self.log_ctx.get("flow")
        run_id = self.log_ctx.get("run_id")
        if flow_name and run_id:
            stub = FlowRecord(name=flow_name, run_id=run_id)
            flow_token = _flow_context.set(stub)
        try:
            with logger.contextualize(**self.log_ctx):
                return self.fn(*args, **kwargs)
        finally:
            if flow_token is not None:
                _flow_context.reset(flow_token)


class ProcessPoolExecutor(concurrent.futures.ProcessPoolExecutor):
    """Drop-in replacement for ``concurrent.futures.ProcessPoolExecutor``.

    Automatically captures the current flow/task log context at ``submit()`` time
    and restores it in each worker process — no changes to worker functions required.

    Usage::

        from atlas.tracing import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=4) as executor:
            executor.submit(my_worker, arg1, arg2)  # context propagated transparently
    """

    def submit(self, fn: Callable, /, *args: Any, **kwargs: Any) -> concurrent.futures.Future:
        ctx = get_log_context()
        if ctx:
            fn = _ContextualWorker(fn, ctx)
        return super().submit(fn, *args, **kwargs)


@dataclass
class TaskRecord:
    name: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: Literal["pending", "running", "success", "failed"] = "pending"
    started_at: pendulum.DateTime | None = None
    ended_at: pendulum.DateTime | None = None
    duration_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
            "error": str(self.error) if self.error else None,
        }


@dataclass
class FlowRecord:
    name: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: Literal["pending", "running", "success", "failed"] = "pending"
    started_at: pendulum.DateTime | None = None
    ended_at: pendulum.DateTime | None = None
    duration_seconds: float | None = None
    tasks: list[TaskRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "tasks": [t.to_dict() for t in self.tasks],
            "metadata": self.metadata,
            "error": str(self.error) if self.error else None,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# @task
# ---------------------------------------------------------------------------


def task(
    _func: F | None = None,
    *,
    name: str | Callable[..., str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Trace a task's execution: duration, status, and metadata.

    Usage::

        @task
        def my_task(): ...

        @task(name="load-data", metadata={"version": "1.0"})
        def load_data(): ...

        # name as a callable — receives the same args as the decorated function
        @task(name=lambda *args: args[1].name)
        def _execute_job(self, job, cis): ...

    The last run record is available via ``my_task.run_record`` (a :class:`TaskRecord`).
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            task_name = name(*args, **kwargs) if callable(name) else (name or func.__name__)
            record = TaskRecord(name=task_name, metadata=dict(metadata or {}))

            flow_record = _flow_context.get()
            if flow_record is not None:
                record.run_id = flow_record.run_id
                flow_record.tasks.append(record)

            ctx: dict[str, str] = {"task": task_name}
            if flow_record is not None:
                ctx["flow"] = flow_record.name
                ctx["run_id"] = flow_record.run_id

            with logger.contextualize(**ctx):
                task_token = _task_context.set(task_name)
                record.status = "running"
                record.started_at = pendulum.now()
                try:
                    result = func(*args, **kwargs)
                    record.status = "success"
                except Exception as e:
                    record.status = "failed"
                    record.error = e
                    raise
                finally:
                    record.ended_at = pendulum.now()
                    if record.started_at is not None:
                        record.duration_seconds = (record.ended_at - record.started_at).total_seconds()
                    _task_context.reset(task_token)
                    wrapper.run_record = record  # type: ignore[attr-defined]

            return result  # type: ignore[possibly-undefined]

        wrapper.run_record = None  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    if _func is not None:
        return decorator(_func)
    return decorator


# ---------------------------------------------------------------------------
# @flow  —  descriptor so that instance.run_record works without store_on
# ---------------------------------------------------------------------------


class _BoundFlow:
    """Bound view of a :class:`_FlowDescriptor` on a specific instance.

    Returned by ``_FlowDescriptor.__get__`` so that ``instance.method()``
    works naturally. After execution ``instance.run_record`` holds the record.
    """

    __slots__ = ("_descriptor", "_instance")

    def __init__(self, descriptor: _FlowDescriptor, instance: Any) -> None:
        self._descriptor = descriptor
        self._instance = instance

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._descriptor._execute(self._instance, args, kwargs)

    @property
    def run_record(self) -> FlowRecord | None:
        return getattr(self._instance, "run_record", self._descriptor.run_record)


class _FlowDescriptor:
    """Descriptor backing :func:`flow`.

    When applied to a class method, ``__set_name__`` is called and the descriptor
    knows it lives on a class. After each call it stores the :class:`FlowRecord`
    directly on the instance (``self.run_record``), with no extra configuration.

    When applied to a plain function ``__set_name__`` is never called, and the
    record is stored on the descriptor itself (``my_flow.run_record``).
    """

    def __init__(
        self,
        func: Callable,
        *,
        name: str | Callable[..., str] | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        self._func = func
        self._name = name
        self._metadata = metadata or {}
        self._is_method = False
        self.run_record: FlowRecord | None = None
        functools.update_wrapper(self, func)

    # Called by Python when the descriptor is assigned inside a class body.
    def __set_name__(self, owner: type, attr_name: str) -> None:
        self._is_method = True

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self  # class-level access → the descriptor itself
        return _BoundFlow(self, obj)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Standalone function call (not a method)."""
        return self._execute(None, args, kwargs)

    def _execute(self, instance: Any, args: tuple, kwargs: dict) -> Any:
        all_args = (instance, *args) if instance is not None else args
        flow_name = self._name(*all_args, **kwargs) if callable(self._name) else (self._name or self._func.__name__)
        record = FlowRecord(name=flow_name, metadata=dict(self._metadata))

        with logger.contextualize(flow=flow_name, run_id=record.run_id):
            record.status = "running"
            record.started_at = pendulum.now()
            token = _flow_context.set(record)
            log_sink_id: int | None = None
            try:
                log_sink_id = _run_store.open_log(record)
                try:
                    result = self._func(*all_args, **kwargs)
                    record.status = "success"
                except Exception as e:
                    record.status = "failed"
                    record.error = e
                    raise
            finally:
                record.ended_at = pendulum.now()
                if record.started_at is not None:
                    record.duration_seconds = (record.ended_at - record.started_at).total_seconds()
                _flow_context.reset(token)
                if instance is not None:
                    try:
                        instance.run_record = record
                    except AttributeError:
                        pass  # __slots__ without run_record — silently skip
                else:
                    self.run_record = record
                try:
                    _run_store.close_log(log_sink_id)
                finally:
                    _run_store.save(record)

        return result  # type: ignore[possibly-undefined]


def flow(
    _func: F | None = None,
    *,
    name: str | Callable[..., str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Trace a flow's execution, aggregating all :func:`task`-decorated calls within it.

    Usage::

        @flow
        def my_pipeline(): ...

        @flow(name="training-pipeline", metadata={"env": "prod"})
        def train(): ...

        # name as a callable — receives the same args as the decorated function
        @flow(name=lambda self: self.parameters.name)
        def execute(self): ...

    When used on a **method**, the :class:`FlowRecord` is stored automatically on
    the instance as ``self.run_record`` after each call — no extra configuration needed::

        workflow.execute()
        workflow.run_record  # FlowRecord

    When used on a **standalone function**, the record is on the function itself::

        my_pipeline()
        my_pipeline.run_record  # FlowRecord
    """
    if _func is not None:
        return _FlowDescriptor(_func, name=name, metadata=metadata)

    def decorator(func: F) -> _FlowDescriptor:
        return _FlowDescriptor(func, name=name, metadata=metadata)

    return decorator


# ---------------------------------------------------------------------------
# RunStore — persists FlowRecord as JSON files
# ---------------------------------------------------------------------------


class RunStore(BaseSettings):
    """Persists :class:`FlowRecord` as JSON and log files after each flow execution.

    Controlled via environment variables with ``RUNS_`` prefix:

    - ``RUNS_ENABLED`` — enable/disable persistence (default: ``true``)
    - ``RUNS_DIR``     — directory for run files (default: ``runs``)
    - ``RUNS_LOG``     — also write a ``.log`` file per run (default: ``true``)
    """

    model_config = SettingsConfigDict(
        env_prefix="RUNS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    enabled: bool = Field(default=True)
    dir: Path = Field(default=Path("runs"))
    log: bool = Field(default=True)
    log_level: str = Field(default="DEBUG")

    def _run_dir(self, record: FlowRecord) -> Path:
        ts = record.started_at.format("YYYYMMDD_HHmmss") if record.started_at else "unknown"
        folder = self.dir / f"{ts}_{record.name}_{record.run_id}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def open_log(self, record: FlowRecord) -> int | None:
        """Add a per-run log sink. Returns the loguru sink ID to pass to :meth:`close_log`."""
        if not self.enabled or not self.log:
            return None
        path = self._run_dir(record) / "run.log"

        def fmt(r: dict) -> str:
            extra = r["extra"]
            parts = [p for p in [extra.get("run_id", ""), extra.get("flow", ""), extra.get("task", "")] if p]
            ctx = (" | ".join(parts) + " | ") if parts else ""
            return "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | " + ctx + "{message}\n"

        return logger.add(str(path), level=self.log_level.upper(), format=fmt, colorize=False)

    def close_log(self, sink_id: int | None) -> None:
        """Remove the per-run log sink opened by :meth:`open_log`."""
        if sink_id is not None:
            logger.remove(sink_id)

    def save(self, record: FlowRecord) -> Path | None:
        """Write *record* to ``{dir}/{started_at}_{name}_{run_id}/record.json``."""
        if not self.enabled:
            return None
        path = self._run_dir(record) / "record.json"
        path.write_text(record.to_json())
        return path


_run_store = RunStore()
