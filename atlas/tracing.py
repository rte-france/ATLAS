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
from pathlib import Path
from typing import Any, Literal, TypeVar

import pendulum
from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

F = TypeVar("F", bound=Callable[..., Any])

_step_context: ContextVar[StepRecord | None] = ContextVar("_step_context", default=None)


def model_to_metadata(model: Any) -> dict[str, Any]:
    """Serialize a Pydantic model to a JSON-safe dict for use as trace metadata.

    Uses ``json.dumps(default=str)`` as a fallback so types like ``pendulum.Duration``
    or ``pathlib.Path`` are represented as their string form rather than raising.
    """
    if not hasattr(model, "model_dump"):
        return {}
    return json.loads(json.dumps(model.model_dump(), default=str))


def get_log_context() -> dict[str, str]:
    """Return the current step/run_id context as a plain dict.

    Useful for advanced cases where you need to propagate context manually.
    For ``ProcessPoolExecutor``, prefer importing it from ``atlas.tracing`` directly —
    it propagates context automatically without any changes to worker functions.
    """
    ctx: dict[str, str] = {}
    record = _step_context.get()
    if record is not None:
        ctx["step"] = record.name
        ctx["run_id"] = record.run_id
    return ctx


class _ContextualWorker:
    """Picklable wrapper that restores the step context in a child process.

    Propagates the parent's step name and ``run_id`` so that ``@step`` calls inside
    the worker emit logs tagged with the parent's run_id. A stub :class:`StepRecord`
    is installed in ``_step_context`` so nested steps see the parent's run_id, but
    their records are **not** aggregated back into the parent (mutations don't cross
    process boundaries). For full aggregation, run inside the parent process.
    """

    __slots__ = ("fn", "log_ctx")

    def __init__(self, fn: Callable, log_ctx: dict[str, str]) -> None:
        self.fn = fn
        self.log_ctx = log_ctx

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        step_token = None
        step_name = self.log_ctx.get("step")
        run_id = self.log_ctx.get("run_id")
        if step_name and run_id:
            stub = StepRecord(name=step_name, run_id=run_id)
            step_token = _step_context.set(stub)
        try:
            with logger.contextualize(**self.log_ctx):
                return self.fn(*args, **kwargs)
        finally:
            if step_token is not None:
                _step_context.reset(step_token)


class ProcessPoolExecutor(concurrent.futures.ProcessPoolExecutor):
    """Drop-in replacement for ``concurrent.futures.ProcessPoolExecutor``.

    Automatically captures the current step context at ``submit()`` time and restores
    it in each worker process — no changes to worker functions required.

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
class StepRecord:
    """Execution record for a single ``@step`` call.

    A root step (no parent in context) owns a unique ``run_id`` and is persisted to
    disk. A child step inherits the parent's ``run_id`` and is embedded in the parent's
    ``children`` list — the whole tree is serialised in a single ``record.json``.
    """

    name: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: Literal["pending", "running", "success", "failed"] = "pending"
    started_at: pendulum.DateTime | None = None
    ended_at: pendulum.DateTime | None = None
    duration_seconds: float | None = None
    children: list[StepRecord] = field(default_factory=list)
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
            "children": [c.to_dict() for c in self.children],
            "metadata": self.metadata,
            "error": str(self.error) if self.error else None,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# @step — descriptor so that instance.run_record works on methods
# ---------------------------------------------------------------------------


class _BoundStep:
    """Bound view of a :class:`_StepDescriptor` on a specific instance."""

    __slots__ = ("_descriptor", "_instance")

    def __init__(self, descriptor: _StepDescriptor, instance: Any) -> None:
        self._descriptor = descriptor
        self._instance = instance

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._descriptor._execute(self._instance, args, kwargs)

    @property
    def run_record(self) -> StepRecord | None:
        return getattr(self._instance, "run_record", self._descriptor.run_record)


class _StepDescriptor:
    """Descriptor backing :func:`step`.

    When applied to a class method, ``__set_name__`` is called and after each call
    the :class:`StepRecord` is stored directly on the instance as ``self.run_record``.

    When applied to a plain function ``__set_name__`` is never called, and the record
    is stored on the descriptor itself (``my_step.run_record``).

    If a parent step is already in context, the new record inherits the parent's
    ``run_id`` and is appended to ``parent.children``. Persistence (log sink +
    ``record.json``) only happens for the root step.
    """

    def __init__(
        self,
        func: Callable,
        *,
        name: str | Callable[..., str] | None,
        metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None,
    ) -> None:
        self._func = func
        self._name = name
        self._metadata: dict[str, Any] | Callable[..., dict[str, Any]] = metadata or {}
        self.run_record: StepRecord | None = None
        functools.update_wrapper(self, func)

    def __set_name__(self, owner: type, attr_name: str) -> None:
        pass  # presence of this method is enough for Python to call it on class body

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        return _BoundStep(self, obj)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._execute(None, args, kwargs)

    def _execute(self, instance: Any, args: tuple, kwargs: dict) -> Any:
        all_args = (instance, *args) if instance is not None else args
        step_name = self._name(*all_args, **kwargs) if callable(self._name) else (self._name or self._func.__name__)
        metadata_val = self._metadata(*all_args, **kwargs) if callable(self._metadata) else self._metadata
        record = StepRecord(name=step_name, metadata=metadata_val)

        parent = _step_context.get()
        if parent is not None:
            record.run_id = parent.run_id
            parent.children.append(record)

        with logger.contextualize(step=step_name, run_id=record.run_id):
            record.status = "running"
            record.started_at = pendulum.now()
            token = _step_context.set(record)
            log_sink_id: int | None = None
            try:
                if parent is None:
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
                _step_context.reset(token)
                if instance is not None:
                    try:
                        instance.run_record = record
                    except AttributeError:
                        pass  # __slots__ without run_record — silently skip
                else:
                    self.run_record = record
                if parent is None:
                    try:
                        _run_store.close_log(log_sink_id)
                    finally:
                        _run_store.save(record)

        return result  # type: ignore[possibly-undefined]


def step(
    _func: F | None = None,
    *,
    name: str | Callable[..., str] | None = None,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None = None,
) -> Any:
    """Trace a step's execution: timing, status, metadata, and hierarchical nesting.

    A step with no parent in context becomes the **root**: it opens a per-run log sink
    and persists a ``record.json`` file when it completes. A step called inside another
    step becomes a **child**: it inherits the parent's ``run_id`` and is embedded in
    ``parent.children`` — no separate file is written.

    Usage::

        @step
        def my_step(): ...

        @step(name="load-data", metadata={"version": "1.0"})
        def load_data(): ...

        # name/metadata as callables — receive the same args as the decorated function
        @step(name=lambda self: self.parameters.name, metadata=lambda self: model_to_metadata(self.parameters))
        def execute(self): ...

    When used on a **method**, the :class:`StepRecord` is stored on the instance::

        workflow.execute()
        workflow.run_record  # StepRecord

    When used on a **standalone function**, the record is on the function itself::

        my_step()
        my_step.run_record  # StepRecord
    """
    if _func is not None:
        return _StepDescriptor(_func, name=name, metadata=metadata)

    def decorator(func: F) -> _StepDescriptor:
        return _StepDescriptor(func, name=name, metadata=metadata)

    return decorator


# ---------------------------------------------------------------------------
# RunStore — persists StepRecord as JSON + log files
# ---------------------------------------------------------------------------


class RunStore(BaseSettings):
    """Persists the root :class:`StepRecord` as JSON and log files after each run.

    Controlled via environment variables with ``RUNS_`` prefix:

    - ``RUNS_ENABLED`` — enable/disable persistence (default: ``true``)
    - ``RUNS_DIR``     — directory for run files (default: ``runs``)
    - ``RUNS_LOG``     — also write a ``run.log`` file per run (default: ``true``)
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

    def _run_dir(self, record: StepRecord) -> Path:
        ts = record.started_at.format("YYYYMMDD_HHmmss") if record.started_at else "unknown"
        folder = self.dir / f"{ts}_{record.name}_{record.run_id}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def open_log(self, record: StepRecord) -> int | None:
        """Add a per-run log sink. Returns the loguru sink ID to pass to :meth:`close_log`."""
        if not self.enabled or not self.log:
            return None
        path = self._run_dir(record) / "run.log"

        def fmt(r: dict) -> str:
            extra = r["extra"]
            parts = [p for p in [extra.get("run_id", ""), extra.get("step", "")] if p]
            ctx = (" | ".join(parts) + " | ") if parts else ""
            return "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | " + ctx + "{message}\n"

        return logger.add(str(path), level=self.log_level.upper(), format=fmt, colorize=False)

    def close_log(self, sink_id: int | None) -> None:
        """Remove the per-run log sink opened by :meth:`open_log`."""
        if sink_id is not None:
            logger.remove(sink_id)

    def save(self, record: StepRecord) -> Path | None:
        """Write *record* to ``{dir}/{started_at}_{name}_{run_id}/record.json``."""
        if not self.enabled:
            return None
        path = self._run_dir(record) / "record.json"
        path.write_text(record.to_json())
        return path


_run_store = RunStore()
