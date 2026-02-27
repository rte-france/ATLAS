"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from loguru import logger as loguru_logger

# Import the Logger class (adjust path as needed)
from atlas.log import Logger


class TestLogger(unittest.TestCase):
    """Unit tests for the Logger class"""

    def setUp(self):
        """Setup test environment before each test"""
        # Save original environment variables to restore them later
        self.original_env = os.environ.copy()

        # Clean up loguru handlers
        loguru_logger.remove()

        # Create a temporary log directory for testing
        self.test_log_dir = Path("test_logs")
        self.test_log_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Clean up after each test"""
        # Restore original environment variables
        os.environ.clear()
        os.environ.update(self.original_env)

        # Clean up test log directory if it exists
        import shutil

        if self.test_log_dir.exists():
            shutil.rmtree(self.test_log_dir)

        # Clean up loguru handlers
        loguru_logger.remove()

    def test_custom_initialization(self):
        """Test Logger initialization with custom environment variables"""
        # Set custom environment variables
        os.environ["LOG_NAME"] = "test_logger"
        os.environ["LOG_LEVEL"] = "DEBUG"
        os.environ["LOG_TO_FILE"] = "true"
        os.environ["LOG_DIR"] = str(self.test_log_dir)
        os.environ["LOG_ROTATION"] = "5 MB"
        os.environ["LOG_RETENTION"] = "1 week"
        os.environ["LOG_FORMAT"] = "{time} {level} {message}"

        logger_instance = Logger()

        self.assertEqual(logger_instance.name, "test_logger")
        self.assertEqual(logger_instance.level, "DEBUG")
        self.assertEqual(logger_instance.to_file, True)
        self.assertEqual(logger_instance.dir, self.test_log_dir)
        self.assertEqual(logger_instance.rotation, "5 MB")
        self.assertEqual(logger_instance.retention, "1 week")
        self.assertEqual(logger_instance.format, "{time} {level} {message}")

    @patch("sys.stdout", new_callable=MagicMock)
    @patch("loguru.logger.add")
    def test_configure_logger_console(self, mock_add, mock_stdout):
        """Test logger configuration for console output"""
        os.environ["LOG_TO_FILE"] = "false"
        os.environ["LOG_LEVEL"] = "WARNING"

        Logger()

        # Check that logger.add was called with stdout
        mock_add.assert_called_once()
        args, kwargs = mock_add.call_args
        self.assertEqual(args[0], sys.stdout)
        self.assertEqual(kwargs["level"], "WARNING")
        self.assertTrue(kwargs["enqueue"])

    @patch("loguru.logger.add")
    def test_configure_logger_file(self, mock_add):
        """Test logger configuration for file output"""
        # Mock pendulum.now() to return a fixed timestamp

        os.environ["LOG_TO_FILE"] = "true"
        os.environ["LOG_NAME"] = "testapp"
        os.environ["LOG_DIR"] = str(self.test_log_dir)
        os.environ["LOG_LEVEL"] = "DEBUG"

        Logger()

        # Check that logger.add was called with a file path
        mock_add.assert_called_once()
        args, kwargs = mock_add.call_args

        self.assertEqual(kwargs["level"], "DEBUG")
        self.assertEqual(kwargs["rotation"], "10 MB")
        self.assertEqual(kwargs["retention"], "2 days")
        self.assertTrue(kwargs["enqueue"])

        # Verify log directory exists
        self.assertTrue(self.test_log_dir.exists())

    def test_get_logger(self):
        """Test get_logger method returns a bound logger"""
        logger_instance = Logger()
        bound_logger = logger_instance.get_logger()

        # Check that the returned object is from loguru
        self.assertTrue(hasattr(bound_logger, "debug"))
        self.assertTrue(hasattr(bound_logger, "info"))
        self.assertTrue(hasattr(bound_logger, "warning"))
        self.assertTrue(hasattr(bound_logger, "error"))
        self.assertTrue(hasattr(bound_logger, "critical"))

    @patch("loguru.logger.bind")
    def test_logger_binding(self, mock_bind):
        """Test that logger is bound with correct name"""
        logger_instance = Logger()
        logger_instance.get_logger()

        mock_bind.assert_called_once_with(logger_name="atlas")

    @patch("pathlib.Path.mkdir")
    def test_log_dir_creation(self, mock_mkdir):
        """Test that log directory is created when logging to file"""
        os.environ["LOG_TO_FILE"] = "true"
        Logger()

        # Check that mkdir was called with parents=True and exist_ok=True
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_functional_console_logging(self):
        """Test that logging to console actually works"""
        # Setup a StringIO object to capture output
        string_io = io.StringIO()

        # Configure environment for console logging
        os.environ["LOG_TO_FILE"] = "false"
        os.environ["LOG_LEVEL"] = "DEBUG"
        # Use a simple format for easier testing
        os.environ["LOG_FORMAT"] = "{level} | {message}"

        # Create logger instance and get bound logger
        logger_instance = Logger()
        test_logger = logger_instance.get_logger()

        # Replace all handlers to redirect output to our StringIO
        loguru_logger.remove()
        loguru_logger.add(string_io, format=logger_instance.format, level=logger_instance.level)

        # Log some test messages
        test_logger.debug("This is a debug message")
        test_logger.info("This is an info message")
        test_logger.warning("This is a warning message")
        test_logger.error("This is an error message")

        # Get the captured output
        output = string_io.getvalue()

        # Verify that messages were logged properly
        self.assertIn("DEBUG | This is a debug message", output)
        self.assertIn("INFO | This is an info message", output)
        self.assertIn("WARNING | This is a warning message", output)
        self.assertIn("ERROR | This is an error message", output)

    def test_log_level_filtering(self):
        """Test that log level filtering works properly"""
        # Setup a StringIO object to capture output
        string_io = io.StringIO()

        # Configure environment for INFO level only
        os.environ["LOG_TO_FILE"] = "false"
        os.environ["LOG_LEVEL"] = "INFO"
        os.environ["LOG_FORMAT"] = "{level} | {message}"

        # Create logger instance and get bound logger
        logger_instance = Logger()
        test_logger = logger_instance.get_logger()

        # Replace all handlers to redirect output to our StringIO
        loguru_logger.remove()
        loguru_logger.add(string_io, format=logger_instance.format, level=logger_instance.level)

        # Log messages at different levels
        test_logger.debug("This is a debug message")
        test_logger.info("This is an info message")
        test_logger.warning("This is a warning message")
        test_logger.error("This is an error message")

        # Get the captured output
        output = string_io.getvalue()

        # Verify DEBUG messages are filtered out but others are included
        self.assertNotIn("DEBUG | This is a debug message", output)
        self.assertIn("INFO | This is an info message", output)
        self.assertIn("WARNING | This is a warning message", output)
        self.assertIn("ERROR | This is an error message", output)

    def test_format_string_application(self):
        """Test that the format string is properly applied to log messages"""
        # Setup a StringIO object to capture output
        string_io = io.StringIO()

        # Configure environment with custom format
        os.environ["LOG_TO_FILE"] = "false"
        os.environ["LOG_FORMAT"] = "TEST-FORMAT: {level} -> {message}"

        # Create logger instance and get bound logger
        logger_instance = Logger()
        test_logger = logger_instance.get_logger()

        # Replace all handlers to redirect output to our StringIO
        loguru_logger.remove()
        loguru_logger.add(string_io, format=logger_instance.format, level=logger_instance.level)

        # Log a test message
        test_logger.info("Test message")

        # Get the captured output
        output = string_io.getvalue()

        # Verify that the format was applied
        self.assertIn("TEST-FORMAT: INFO -> Test message", output)

    def test_logger_binding_values(self):
        """Test that bound values are included in log messages"""
        # Setup a StringIO object to capture output
        string_io = io.StringIO()

        # Configure environment with format that includes extra fields
        os.environ["LOG_TO_FILE"] = "false"
        os.environ["LOG_FORMAT"] = "{level} | {extra[logger_name]} | {message}"

        # Create logger instance and get bound logger
        logger_instance = Logger()
        test_logger = logger_instance.get_logger()

        # Replace all handlers to redirect output to our StringIO
        loguru_logger.remove()
        loguru_logger.add(string_io, format=logger_instance.format, level=logger_instance.level)

        # Log a test message
        test_logger.info("Test message with bound value")

        # Get the captured output
        output = string_io.getvalue()

        # Verify that the bound value is in the output
        self.assertIn("INFO | atlas | Test message with bound value", output)
