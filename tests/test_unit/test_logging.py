"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import io
import os
import unittest

from loguru import logger

from atlas.log import LoggerSettings, configure_logging, format_context_prefix


class TestLoggerSettings(unittest.TestCase):
    """LoggerSettings reads LOG_* env vars."""

    def setUp(self):
        self.original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_defaults(self):
        for key in ("LOG_LEVEL", "LOG_FORMAT"):
            os.environ.pop(key, None)
        settings = LoggerSettings()
        self.assertEqual(settings.level, "INFO")
        self.assertIn("{message}", settings.format)

    def test_reads_env_vars(self):
        os.environ["LOG_LEVEL"] = "DEBUG"
        os.environ["LOG_FORMAT"] = "{time} {level} {message}"
        settings = LoggerSettings()
        self.assertEqual(settings.level, "DEBUG")
        self.assertEqual(settings.format, "{time} {level} {message}")


class TestConfigureLogging(unittest.TestCase):
    """configure_logging installs a stdout sink that respects level + format."""

    def setUp(self):
        logger.remove()

    def tearDown(self):
        logger.remove()

    def _capture_logs(self, level: str, format_str: str) -> io.StringIO:
        buf = io.StringIO()
        logger.remove()
        logger.add(buf, level=level, format=format_str)
        return buf

    def test_level_filtering(self):
        buf = self._capture_logs("INFO", "{level} | {message}")
        logger.debug("dbg")
        logger.info("info")
        logger.warning("warn")
        output = buf.getvalue()
        self.assertNotIn("dbg", output)
        self.assertIn("INFO | info", output)
        self.assertIn("WARNING | warn", output)

    def test_format_applied(self):
        buf = self._capture_logs("DEBUG", "TEST: {level} -> {message}")
        logger.info("hello")
        self.assertIn("TEST: INFO -> hello", buf.getvalue())


class TestFormatContextPrefix(unittest.TestCase):
    """format_context_prefix builds a ' | '-joined prefix from extra fields."""

    def test_empty_extra(self):
        self.assertEqual(format_context_prefix({}), "")

    def test_run_id_only(self):
        self.assertEqual(format_context_prefix({"run_id": "abc"}), "abc | ")

    def test_step_only(self):
        self.assertEqual(format_context_prefix({"step": "outer | inner"}), "outer | inner | ")

    def test_run_id_and_step(self):
        self.assertEqual(
            format_context_prefix({"run_id": "abc", "step": "outer"}),
            "abc | outer | ",
        )

    def test_decorate(self):
        decorate = lambda kind, val: f"[{kind}={val}]"
        self.assertEqual(
            format_context_prefix({"run_id": "abc", "step": "x"}, decorate),
            "[run_id=abc] | [step=x] | ",
        )


class TestConfigureLoggingIntegration(unittest.TestCase):
    """End-to-end: configure_logging + logger.contextualize produces expected prefix."""

    def setUp(self):
        self.original_env = os.environ.copy()
        logger.remove()

    def tearDown(self):
        logger.remove()
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_context_prefix_in_output(self):
        os.environ["LOG_LEVEL"] = "DEBUG"
        os.environ["LOG_FORMAT"] = "{level} | {message}"
        configure_logging()

        buf = io.StringIO()
        logger.add(buf, level="DEBUG", format=lambda r: f"{format_context_prefix(r['extra'])}{r['message']}\n")
        with logger.contextualize(run_id="abc", step="root | child"):
            logger.info("hello")

        self.assertIn("abc | root | child | hello", buf.getvalue())
