"""
Pytest configuration and shared fixtures for ATLAS tests.

This module provides shared fixtures and utilities for testing ATLAS,
including handling of commercial solvers that require licenses.
"""

import os
from pathlib import Path

import pytest
from ortools.linear_solver import pywraplp

from tests.utils import TIMINGS, format_timings


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """
    Report the execution times measured by performance tests against their thresholds.

    On GitHub Actions the table is also added to the job summary, so it shows on the run page.
    """
    if not TIMINGS:
        return
    terminalreporter.section("execution times")
    for line in format_timings(TIMINGS):
        terminalreporter.write_line(line)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with Path(step_summary).open("a") as summary:
            summary.write("\n".join(["### Execution times", "", *format_timings(TIMINGS, markdown=True), ""]) + "\n")


def is_xpress_available() -> bool:
    """Check if XPRESS solver is available (requires license).

    XPRESS is a commercial optimization solver that requires a valid license.
    This function attempts to create an XPRESS solver instance to verify
    if it's available in the current environment.

    :return: True if XPRESS solver can be created, False otherwise
    :rtype: bool
    """
    try:
        solver = pywraplp.Solver.CreateSolver("xpress")
        return solver is not None
    except Exception:
        return False


@pytest.fixture
def xpress_available() -> bool:
    """Fixture that returns whether XPRESS solver is available.

    Use this fixture in tests that need to conditionally execute
    based on XPRESS availability.
    """
    return is_xpress_available()


# Create a skip marker for tests requiring XPRESS
# Usage: Decorate tests with @requires_xpress to skip them when XPRESS is unavailable
# Example:
#   @requires_xpress
#   def test_xpress_specific_feature():
#       model = OptimisationModel(solver_name=SolverEnum.XPRESS)
#       ...
requires_xpress = pytest.mark.skipif(not is_xpress_available(), reason="XPRESS solver not available (requires license)")
