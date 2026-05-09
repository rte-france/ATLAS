"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements the Atlas logger.
"""

import sys
from collections.abc import Callable

from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def format_context_prefix(extra: dict, decorate: Callable[[str, str], str] | None = None) -> str:
    """Return a ``" | "``-joined prefix from ``extra['run_id']`` and ``extra['step']``.

    Both values are populated by ``atlas.tracing`` via ``logger.contextualize(...)``.
    Pass ``decorate(kind, value) -> str`` to wrap each part (e.g. with loguru tags
    for colored console output). Returns ``""`` when neither key is set.
    """
    wrap = decorate or (lambda _kind, val: val)
    parts: list[str] = []
    run_id = extra.get("run_id", "")
    if run_id:
        parts.append(wrap("run_id", run_id))
    step = extra.get("step", "")
    if step:
        parts.append(wrap("step", step))
    return " | ".join(parts) + " | " if parts else ""


def _make_context_format(base: str) -> Callable[[dict], str]:
    """Wrap a loguru format string to inject run_id and step path as pipe-separated columns."""

    def _decorate(kind: str, value: str) -> str:
        return f"<dim>{value}</dim>" if kind == "run_id" else f"<bold>{value}</bold>"

    def format_record(record: dict) -> str:
        ctx = format_context_prefix(record["extra"], _decorate)
        if "<level>{message}</level>" in base:
            return base.replace("<level>{message}</level>", f"{ctx}<level>{{message}}</level>") + "\n"
        return base.replace("{message}", ctx + "{message}") + "\n"

    return format_record


class Logger(BaseSettings):
    """
    A configurable logger using Loguru, suitable for project-wide use.

    Logging configuration can be controlled via environment variables with LOG_ prefix:

    - LOG_LEVEL:  logging level (e.g., DEBUG, INFO, WARNING)
    - LOG_FORMAT: log message format string
    - LOG_NAME:   name of the logger (default: "atlas")

    Per-run log files are handled by :class:`atlas.tracing.RunStore`.
    """

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    name: str = Field(default="atlas", description="Name of the logger")
    level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    format: str = Field(
        default="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
        description="Log message format string",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.level = self.level.upper()
        self._configure_logger()

    def _configure_logger(self) -> None:
        logger.remove()
        logger.add(
            sys.stdout,
            level=self.level,
            format=_make_context_format(self.format),
            enqueue=True,
        )

    def get_logger(self):  # noqa: ANN201
        """
        Returns a bound logger instance, pre-configured.

        :return: A Loguru logger instance.
        :rtype: loguru.logger
        """
        return logger.bind(logger_name=self.name)
