import os
import sys
from pathlib import Path

import pendulum
from loguru import logger


class Logger:
    """
    A configurable logger using Loguru, suitable for project-wide use.

    Logging configuration can be controlled via environment variables:

    - LOG_LEVEL: logging level (e.g., DEBUG, INFO, WARNING)
    - LOG_TO_FILE: enable file logging ("true" / "false")
    - LOG_DIR: directory to store logs
    - LOG_ROTATION: log rotation policy (e.g., "10 MB", "1 week")
    - LOG_RETENTION: log retention policy (e.g., "7 days", "1 month")

    :param name: Identifier for the logger and log file prefix.
    :type name: str
    :param level: Minimum logging level (e.g., "INFO", "DEBUG").
    :type level: str
    :param log_to_file: Whether to write logs to a file.
    :type log_to_file: bool
    :param log_dir: Directory to save log files.
    :type log_dir: str
    :param rotation: File rotation size/time for logs.
    :type rotation: str
    :param retention: Retention policy for old log files.
    :type retention: str
    :param format_str: Format string for log entries.
    :type format_str: str
    """

    def __init__(  # noqa: PLR0913
        self,
        name: str = "default",
        level: str = "INFO",
        log_to_file: bool = True,
        log_dir: str = "logs",
        rotation: str = "10 MB",  # e.g. "500 MB", "1 week"
        retention: str = "7 days",  # e.g. "10 days", "1 month"
        format_str: str = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    ):
        self.name = name
        self.level = level or os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_to_file = (
            log_to_file
            if log_to_file is not None
            else os.getenv("LOG_TO_FILE", "false").lower() == "true"
        )
        self.log_dir = Path(log_dir or os.getenv("LOG_DIR", "logs"))
        self.rotation = rotation or os.getenv("LOG_ROTATION", "10 MB")
        self.retention = retention or os.getenv("LOG_RETENTION", "7 days")
        self.format_str = format_str or (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        )
        self._configure_logger()

    def _configure_logger(self) -> None:
        logger.remove()

        # Console sink
        logger.add(
            sys.stdout,
            level=self.level,
            format=self.format_str,
            enqueue=True,
        )

        # File sink
        if self.log_to_file:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = pendulum.now().strftime("%Y%m%d_%H%M%S")

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
