"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import os
import sys
from pathlib import Path

import pendulum
from dotenv import load_dotenv
from loguru import logger

load_dotenv(".env")


class Logger:
    """
    A configurable logger using Loguru, suitable for project-wide use.

    Logging configuration can be controlled via environment variables:

    - LOG_LEVEL: logging level (e.g., DEBUG, INFO, WARNING)
    - LOG_TO_FILE: enable file logging ("true" / "false")
    - LOG_DIR: directory to store logs
    - LOG_ROTATION: log rotation policy (e.g., "10 MB", "1 week")
    - LOG_RETENTION: log retention policy (e.g., "7 days", "1 month")
    - LOG_FORMAT: log message format string
    - LOG_NAME: name of the logger (default: "atlas")
    """

    def __init__(self):
        self.name = os.getenv("LOG_NAME", "atlas")
        self.level = os.getenv("LOG_LEVEL", "INFO")
        self.log_to_file = os.getenv("LOG_TO_FILE", "false")

        self.log_dir = Path(os.getenv("LOG_DIR", Path("logs")))
        self.rotation = os.getenv("LOG_ROTATION", "10 MB")
        self.retention = os.getenv("LOG_RETENTION", "2 days")
        self.format_str = os.getenv(
            "LOG_FORMAT",
            "<green>{time:HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>",
        )
        self._configure_logger()

    def _configure_logger(self) -> None:
        logger.remove()

        if self.log_to_file.lower() == "false":
            logger.add(
                sys.stdout,
                level=self.level.upper(),
                format=self.format_str,
                enqueue=True,
            )
        else:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = pendulum.now().to_datetime_string()

            log_file = self.log_dir / f"{self.name}-{timestamp}.log"

            logger.add(
                log_file,
                level=self.level,
                format=self.format_str,
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
