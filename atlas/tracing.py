"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

import concurrent.futures
import functools
import json
import traceback as tb_module
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast, overload

import pendulum
from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from atlas.log import format_context_prefix, with_context

STEP_PATH_SEPARATOR = " | "

_step_context: ContextVar[StepRecord | None] = ContextVar("_step_context", default=None)


def model_to_metadata(model: Any) -> dict[str, Any]:
    """Serialize a Pydantic model to a JSON-safe dict for use as trace metadata.

    Uses ``json.dumps(default=str)`` as a fallback so types like ``pendulum.Duration``
    or ``pathlib.Path`` are represented as their string form rather than raising.
    """
    if not hasattr(model, "model_dump"):
        return {}
    return json.loads(json.dumps(model.model_dump(), default=str))


def _contextualize(run_id: str = "", step: str = "") -> Any:
    """``logger.contextualize`` with the log prefix precomputed once (not per message)."""
    ctx = format_context_prefix({"run_id": run_id, "step": step})
    return logger.contextualize(run_id=run_id, step=step, ctx=ctx)


def get_log_context() -> dict[str, str]:
    """Return the current step path and ``run_id`` as a plain dict.

    Useful for advanced cases where you need to propagate context manually.
    For ``ProcessPoolExecutor``, prefer importing it from ``atlas.tracing`` directly —
    it propagates context automatically without any changes to worker functions.
    """
    record = _step_context.get()
    if record is None:
        return {}
    return {"step": record.path, "run_id": record.run_id}


@dataclass
class StepRecord:
    """Execution record for a single ``@step`` call.

    A root step (``parent is None``) owns a unique ``run_id`` and is persisted to
    disk. A child step inherits the parent's ``run_id`` and is appended to the
    parent's ``children`` list — the whole tree is serialised in one ``record.json``.
    """

    name: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: Literal["pending", "running", "success", "failed"] = "pending"
    started_at: pendulum.DateTime | None = None
    ended_at: pendulum.DateTime | None = None
    children: list[StepRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None
    traceback: str | None = None
    parent: StepRecord | None = field(default=None, repr=False, compare=False)

    @property
    def is_root(self) -> bool:
        return self.parent is None

    @property
    def path(self) -> str:
        """``" | "``-joined chain of names from the root step down to this one."""
        names: list[str] = []
        node: StepRecord | None = self
        while node is not None:
            names.append(node.name)
            node = node.parent
        return STEP_PATH_SEPARATOR.join(reversed(names))

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None or self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()

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
            "traceback": self.traceback,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class _ContextualWorker:
    """Picklable wrapper that restores the step context in a child process.

    Rebuilds a parent chain of stub :class:`StepRecord` nodes from the dotted path
    so that nested ``@step`` calls inside the worker produce the correct full path
    and inherit the parent's ``run_id``. Mutations don't cross process boundaries,
    so child records are not aggregated back into the parent.
    """

    __slots__ = ("fn", "log_ctx")

    def __init__(self, fn: Callable, log_ctx: dict[str, str]) -> None:
        self.fn = fn
        self.log_ctx = log_ctx

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        step_path = self.log_ctx.get("step", "")
        run_id = self.log_ctx.get("run_id")
        token = None
        if step_path and run_id:
            node: StepRecord | None = None
            for name in step_path.split(STEP_PATH_SEPARATOR):
                node = StepRecord(name=name, run_id=run_id, parent=node)
            token = _step_context.set(node)
        try:
            with _contextualize(**self.log_ctx):
                return self.fn(*args, **kwargs)
        finally:
            if token is not None:
                _step_context.reset(token)


class ProcessPoolExecutor(concurrent.futures.ProcessPoolExecutor):
    """Drop-in replacement for ``concurrent.futures.ProcessPoolExecutor``.

    Captures the current step context at ``submit()`` time and restores it in each
    worker process — no changes to worker functions required.

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


class _StepDescriptor:
    """Descriptor backing :func:`step`.

    On a method, the :class:`StepRecord` is stored on the instance as ``run_record``.
    On a plain function, it is stored on the descriptor itself.

    If a parent step is in context, the new record inherits the parent's ``run_id``
    and is appended to ``parent.children``. Persistence (log sink + ``record.json``)
    only happens for the root step.
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

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self

        @functools.wraps(self._func)
        def bound(*args: Any, **kwargs: Any) -> Any:
            return self._execute(obj, args, kwargs)

        return bound

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._execute(None, args, kwargs)

    def _execute(self, instance: Any, args: tuple, kwargs: dict) -> Any:
        all_args = (instance, *args) if instance is not None else args
        name = self._name(*all_args, **kwargs) if callable(self._name) else (self._name or self._func.__name__)
        metadata = self._metadata(*all_args, **kwargs) if callable(self._metadata) else self._metadata

        parent = _step_context.get()
        record = StepRecord(name=name, metadata=metadata, parent=parent)
        if parent is not None:
            record.run_id = parent.run_id
            parent.children.append(record)

        record.status = "running"
        record.started_at = pendulum.now()
        ctx_token = _step_context.set(record)

        with _contextualize(run_id=record.run_id, step=record.path):
            sink_id: int | None = None
            try:
                if record.is_root:
                    sink_id = _run_store.open_log(record)
                result = self._func(*all_args, **kwargs)
                record.status = "success"
                return result
            except Exception as e:
                record.status = "failed"
                record.error = e
                record.traceback = tb_module.format_exc()
                raise
            finally:
                record.ended_at = pendulum.now()
                _step_context.reset(ctx_token)
                self._publish(record, instance)
                if record.is_root:
                    try:
                        _run_store.close_log(sink_id)
                    finally:
                        _run_store.save(record)

    def _publish(self, record: StepRecord, instance: Any) -> None:
        if instance is None:
            self.run_record = record
            return
        try:
            instance.run_record = record
        except AttributeError:
            logger.debug(
                f"Cannot store run_record on {type(instance).__name__} (likely __slots__ without 'run_record')"
            )


@overload
def step[F: Callable[..., Any]](
    _func: F,
    *,
    name: str | Callable[..., str] | None = None,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None = None,
) -> F: ...


@overload
def step[F: Callable[..., Any]](
    _func: None = None,
    *,
    name: str | Callable[..., str] | None = None,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None = None,
) -> Callable[[F], F]: ...


def step[F: Callable[..., Any]](
    _func: F | None = None,
    *,
    name: str | Callable[..., str] | None = None,
    metadata: dict[str, Any] | Callable[..., dict[str, Any]] | None = None,
) -> F | Callable[[F], F]:
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

    When used on a **standalone function**, the record is on the function itself; read it with
    :func:`run_record_of`, which mypy can type::

        my_step()
        run_record_of(my_step)  # StepRecord
    """
    # The descriptor behaves like the function it wraps (same arguments, same result, bound on an instance),
    # so the decorated callable keeps its own type: mypy checks its calls and names it in its messages.
    if _func is not None:
        return cast(F, _StepDescriptor(_func, name=name, metadata=metadata))

    def decorator(func: F) -> F:
        return cast(F, _StepDescriptor(func, name=name, metadata=metadata))

    return decorator


def run_record_of(func: Callable[..., Any]) -> StepRecord | None:
    """Return the record of the last run of a function decorated with :func:`step`, or None if it never ran.

    Equivalent to ``func.run_record``, which mypy cannot type: :func:`step` keeps the type of the function so that
    mypy checks its calls, and a function type has no ``run_record`` attribute. On a method, read the record on the
    instance instead (``workflow.run_record``).
    """
    return getattr(func, "run_record", None)


class RunStore(BaseSettings):
    """Persists the root :class:`StepRecord` as JSON and log files after each run.

    Controlled via environment variables with ``RUN_RECORD_`` prefix:

    - ``RUN_RECORD_ENABLED`` — enable/disable persistence (default: ``false``)
    - ``RUN_RECORD_DIR``     — directory for run files (default: ``runs``)
    - ``RUN_RECORD_LOG``     — also write a ``run.log`` file per run (default: ``true``)
    """

    model_config = SettingsConfigDict(
        env_prefix="RUN_RECORD_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    enabled: bool = Field(default=False)
    dir: Path = Field(default=Path("runs"))
    log: bool = Field(default=True)
    log_level: str = Field(default="INFO")

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
        fmt = with_context("{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}")
        return logger.add(str(path), level=self.log_level.upper(), format=fmt, colorize=False, enqueue=True)

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
