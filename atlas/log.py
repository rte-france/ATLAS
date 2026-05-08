"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements the Atlas logger.
"""

import sys
from collections.abc import Callable
from pathlib import Path

import pendulum
from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _make_context_format(base: str) -> Callable[[dict], str]:
    """Wrap a loguru format string to inject flow/task as pipe-separated columns."""

    def format_record(record: dict) -> str:
        extra = record["extra"]
        run_id = extra.get("run_id", "")
        flow_name = extra.get("flow", "")
        task = extra.get("task", "")

        parts: list[str] = []
        if run_id:
            parts.append(f"<dim>{run_id}</dim>")
        if flow_name:
            parts.append(f"<bold>{flow_name}</bold>")
        if task:
            parts.append(f"<bold>{task}</bold>")

        ctx = (" | ".join(parts) + " | ") if parts else ""

        if "<level>{message}</level>" in base:
            return base.replace("<level>{message}</level>", f"{ctx}<level>{{message}}</level>") + "\n"
        return base.replace("{message}", ctx + "{message}") + "\n"

    return format_record


class Logger(BaseSettings):
    """
    A configurable logger using Loguru, suitable for project-wide use.

    Logging configuration can be controlled via environment variables with LOG_ prefix:

    - LOG_LEVEL: logging level (e.g., DEBUG, INFO, WARNING)
    - LOG_TO_FILE: enable file logging (true/false)
    - LOG_DIR: directory to store logs
    - LOG_ROTATION: log rotation policy (e.g., "10 MB", "1 week")
    - LOG_RETENTION: log retention policy (e.g., "7 days", "1 month")
    - LOG_FORMAT: log message format string
    - LOG_NAME: name of the logger (default: "atlas")
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
    to_file: bool = Field(default=False, description="Enable file logging")
    dir: Path = Field(default=Path("logs"), description="Directory to store log files")
    rotation: str = Field(default="10 MB", description="Log rotation policy")
    retention: str = Field(default="2 days", description="Log retention policy")
    format: str = Field(
        default="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
        description="Log message format string",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Normalize level to uppercase for consistency with loguru
        self.level = self.level.upper()
        self._configure_logger()

    def _configure_logger(self) -> None:
        logger.remove()

        fmt = _make_context_format(self.format)

        logger.add(
            sys.stdout,
            level=self.level,
            format=fmt,
            enqueue=True,
        )
        if self.to_file:
            self.dir.mkdir(parents=True, exist_ok=True)
            timestamp = pendulum.now().format("YYYY-MM-DD-HH-mm-ss")

            log_file = self.dir / f"{self.name}-{timestamp}.log"

            logger.add(
                log_file,
                level=self.level,
                format=fmt,
                rotation=self.rotation,
                retention=self.retention,
                enqueue=True,
            )

    def get_logger(self):  # noqa: ANN201
        """
        Returns a bound logger instance, pre-configured.

        :return: A Loguru logger instance.
        :rtype: loguru.logger
        """
        return logger.bind(logger_name=self.name)
