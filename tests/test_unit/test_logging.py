# test_logger.py


import pytest
from loguru import logger as loguru_logger

from atlas.logging import Logger


@pytest.fixture(autouse=True)
def clear_loguru_handlers():
    # Remove all Loguru handlers to avoid duplicates between tests
    loguru_logger.remove()
    yield
    loguru_logger.remove()


def test_stdout_logger(monkeypatch, capsys):
    monkeypatch.setenv("LOG_NAME", "testlog")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_TO_FILE", "false")

    log = Logger().get_logger()
    log.info("Hello from test!")

    captured = capsys.readouterr()
    assert "Hello from test!" in captured.out


def test_file_logger(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_NAME", "filelog")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_TO_FILE", "true")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_ROTATION", "1 MB")
    monkeypatch.setenv("LOG_RETENTION", "1 day")

    log = Logger().get_logger()
    log.info("Log to file test")

    # Look for a log file created in tmp_path
    log_files = list(tmp_path.glob("filelog-*.log"))
    assert len(log_files) == 1

    log_content = log_files[0].read_text()
    assert "Log to file test" in log_content


def test_log_format(monkeypatch, capsys):
    monkeypatch.setenv("LOG_TO_FILE", "false")
    monkeypatch.setenv("LOG_FORMAT", "<level>{message}</level>")

    log = Logger().get_logger()
    log.warning("Formatted log message")

    captured = capsys.readouterr()
    assert captured.out == "Formatted log message\n"
