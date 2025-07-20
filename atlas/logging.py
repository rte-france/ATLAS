"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements the Atlas logger.
"""

import sys
from pathlib import Path

import pendulum
from loguru import logger
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        self._configure_logger()

    @property
    def log_to_file(self) -> str:
        """Backwards compatibility property for file logging flag."""
        return "true" if self.to_file else "false"

    @property
    def log_dir(self) -> Path:
        """Backwards compatibility property for log directory."""
        return self.dir

    @property
    def format_str(self) -> str:
        """Backwards compatibility property for log format."""
        return self.format

    def _configure_logger(self) -> None:
        logger.remove()

        if not self.to_file:
            logger.add(
                sys.stdout,
                level=self.level.upper(),
                format=self.format,
                enqueue=True,
            )
        else:
            self.dir.mkdir(parents=True, exist_ok=True)
            timestamp = pendulum.now().to_datetime_string()

            log_file = self.dir / f"{self.name}-{timestamp}.log"

            logger.add(
                log_file,
                level=self.level.upper(),
                format=self.format,
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
