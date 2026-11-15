"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that configures the Atlas stdout logger sink.
"""

import sys

from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def format_context_prefix(extra: dict) -> str:
    """Return a ``" | "``-joined prefix from ``extra['run_id']`` and ``extra['step']``.

    Computed once per step by ``atlas.tracing`` and stored in ``extra['ctx']``, so sinks
    use a static format string (parsed once by loguru) instead of a per-message callable.
    Returns ``""`` when neither key is set.
    """
    parts = [v for v in (extra.get("run_id"), extra.get("step")) if v]
    return " | ".join(parts) + " | " if parts else ""


def with_context(fmt: str) -> str:
    """Insert the precomputed ``{extra[ctx]}`` prefix right before ``{message}`` in *fmt*."""
    return fmt.replace("{message}", "{extra[ctx]}{message}", 1)


# Default so ``{extra[ctx]}`` resolves outside any step.
logger.configure(extra={"ctx": ""})


class LoggerSettings(BaseSettings):
    """Env-driven logging configuration.

    Read from environment variables with ``LOG_`` prefix:

    - ``LOG_LEVEL``  — logging level (default: ``INFO``)
    - ``LOG_FORMAT`` — loguru format string for the stdout sink
    """

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")
    format: str = Field(
        default="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
        description="Log message format string",
    )

    @field_validator("level")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


def configure_logging(settings: LoggerSettings | None = None) -> None:
    """Install the stdout sink. Call once at app startup.

    Replaces all existing loguru handlers, so call this **before** any per-run sinks
    (e.g. those added by :class:`atlas.tracing.RunStore`).
    """
    settings = settings or LoggerSettings()
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.level,
        format=with_context(settings.format),
        enqueue=True,
    )
