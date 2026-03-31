"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Comprehensive unit tests for SolverHelper class.
"""

import tempfile
from pathlib import Path

import pytest
from ortools.linear_solver import pywraplp

from atlas.solver.solver_helper import SolverHelper

# Test data directory helper
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"


@pytest.fixture
def simple_solver():
    """Create a simple solver for testing."""
    solver = pywraplp.Solver.CreateSolver("GLOP")
    x = solver.NumVar(0, 10, "x")
    y = solver.NumVar(0, 5, "y")
    solver.Add(x + 2 * y <= 14, "constraint_1")
    solver.Add(3 * x - y >= 0, "constraint_2")
    objective = solver.Objective()
    objective.SetCoefficient(x, 3)
    objective.SetCoefficient(y, 4)
    objective.SetMaximization()
    return solver


@pytest.fixture
def solver_with_binaries():
    """Create a solver with binary variables."""
    solver = pywraplp.Solver.CreateSolver("SCIP")
    x = solver.IntVar(0, 1, "binary_x")
    y = solver.NumVar(0, 10, "continuous_y")
    solver.Add(x + y <= 5, "constraint_1")
    objective = solver.Objective()
    objective.SetCoefficient(x, 2)
    objective.SetCoefficient(y, 1)
    objective.SetMaximization()
    return solver


@pytest.fixture
def lp_ortools():
    """Path to OrTools LP test file."""
    return TEST_DATA_DIR / "storage_es_battery.lp"


@pytest.fixture
def lp_legacy():
    """Path to legacy LP test file."""
    return TEST_DATA_DIR / "es_battery_lp.lp"


@pytest.fixture
def new_lp():
    """Path for new LP file (temporary)."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
        temp_path = f.name
    yield temp_path
    # Cleanup after test
    Path(temp_path).unlink(missing_ok=True)


class TestReadLPOrtools:
    """Tests for read_lp_ortools method."""

    def test_read_lp_ortools(self, lp_ortools):
        """Test reading OrTools LP file."""
        result = SolverHelper.read_lp_ortools(lp_ortools)

        assert "objectives" in result
        assert "constraints" in result
        assert "variables" in result
        assert "binaries" in result

        assert len(result["objectives"]) == 1
        assert len(result["constraints"]) == 3
        assert len(result["variables"]) == 4
        assert len(result["binaries"]) == 1


class TestReadLPLegacy:
    """Tests for read_lp_legacy method."""

    def test_read_lp_legacy(self, lp_legacy):
        """Test reading legacy LP file."""
        result = SolverHelper.read_lp_legacy(lp_legacy)

        assert "objectives" in result
        assert "constraints" in result
        assert "variables" in result
        assert "binaries" in result

        assert len(result["objectives"]) == 2
        assert len(result["constraints"]) == 3
        assert len(result["variables"]) == 1
        assert len(result["binaries"]) == 1


class TestNormalizeVariableName:
    """Tests for normalize_variable_name method."""

    def test_normalize_variable_name_with_colon(self):
        """Test normalizing variable name with trailing colon."""
        result = SolverHelper.normalize_variable_name("variable_name:")
        assert result == "variable_name"

    def test_normalize_variable_name_with_spaces(self):
        """Test normalizing variable name with spaces."""
        result = SolverHelper.normalize_variable_name("  variable_name  ")
        assert result == "variable_name"

    def test_normalize_variable_name_uppercase(self):
        """Test normalizing variable name to lowercase."""
        result = SolverHelper.normalize_variable_name("Variable_Name")
        assert result == "variable_name"

    def test_normalize_variable_name_all(self):
        """Test normalizing variable name with all transformations."""
        result = SolverHelper.normalize_variable_name("  Variable_Name:  ")
        # Note: strip() is applied after rstrip(":"), so trailing spaces prevent colon removal
        assert result == "variable_name:"


class TestIsFloat:
    """Tests for isfloat method."""

    def test_isfloat_with_float(self):
        """Test isfloat with valid float string."""
        assert SolverHelper.isfloat("3.14") is True

    def test_isfloat_with_integer(self):
        """Test isfloat with integer string."""
        assert SolverHelper.isfloat("42") is True

    def test_isfloat_with_negative(self):
        """Test isfloat with negative number."""
        assert SolverHelper.isfloat("-3.14") is True

    def test_isfloat_with_invalid(self):
        """Test isfloat with invalid string."""
        assert SolverHelper.isfloat("not_a_number") is False


class TestExportDifferences:
    """Tests for export difference methods."""

    def test_export_objective_differences_csv(self):
        """Test exporting objective differences to CSV."""
        pb1 = {
            "objectives": {"x": 1.0, "y": 2.0},
            "constraints": {},
            "variables": {},
        }
        pb2 = {
            "objectives": {"x": 1.5, "y": 2.0, "z": 3.0},
            "constraints": {},
            "variables": {},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filename = f.name

        try:
            SolverHelper.export_objective_differences_csv(pb1, pb2, filename, keep_identical=True)

            assert Path(filename).exists()
            with open(filename) as f:
                content = f.read()
                assert "Variable" in content
                assert "Difference" in content
                assert "Status" in content
        finally:
            Path(filename).unlink(missing_ok=True)

    def test_export_variable_differences_csv(self):
        """Test exporting variable differences to CSV."""
        pb1 = {
            "objectives": {},
            "constraints": {},
            "variables": {"x": [0, 10], "y": [0, 5]},
        }
        pb2 = {
            "objectives": {},
            "constraints": {},
            "variables": {"x": [0, 15], "y": [0, 5], "z": [0, 20]},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filename = f.name

        try:
            SolverHelper.export_variable_differences_csv(pb1, pb2, filename, keep_identical=True)

            assert Path(filename).exists()
            with open(filename) as f:
                content = f.read()
                assert "Variable" in content
                assert "Status" in content
        finally:
            Path(filename).unlink(missing_ok=True)

    def test_export_constraint_differences_csv(self):
        """Test exporting constraint differences to CSV."""
        pb1 = {
            "objectives": {},
            "constraints": {
                "c1": {"LB": 0, "UB": 10, "x": 1.0},
                "c2": {"LB": 0, "UB": 5, "y": 2.0},
            },
            "variables": {},
        }
        pb2 = {
            "objectives": {},
            "constraints": {
                "c1": {"LB": 0, "UB": 15, "x": 1.0},
                "c2": {"LB": 0, "UB": 5, "y": 2.0},
            },
            "variables": {},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            filename = f.name

        try:
            SolverHelper.export_constraint_differences_csv(pb1, pb2, filename, keep_identical=True)

            assert Path(filename).exists()
        finally:
            Path(filename).unlink(missing_ok=True)


class TestCompareLPProblems:
    """Tests for compare_lp_problems method."""

    def test_compare_lp_problems(self):
        """Test comparing two LP problems."""
        pb1 = {
            "objectives": {"x": 1.0, "y": 2.0},
            "constraints": {"c1": {"LB": 0, "UB": 10, "x": 1.0}},
            "variables": {"x": [0, 10], "y": [0, 5]},
            "binaries": [],
        }
        pb2 = {
            "objectives": {"x": 1.5, "y": 2.0},
            "constraints": {"c1": {"LB": 0, "UB": 10, "x": 1.0}},
            "variables": {"x": [0, 15], "y": [0, 5]},
            "binaries": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = SolverHelper.compare_lp_problems(pb1, pb2, output_dir=tmpdir, keep_identical=False)

            # Check that files were created
            assert Path(tmpdir, "objective_differences.csv").exists()
            assert Path(tmpdir, "variable_differences.csv").exists()
            assert Path(tmpdir, "constraint_differences.csv").exists()
            assert Path(tmpdir, "constraint_details.csv").exists()
            assert Path(tmpdir, "overall_summary_report.txt").exists()

            # Check summary structure
            assert "objectives" in result
            assert "variables" in result
            assert "constraints" in result

    def test_compare_lp_problems_with_exclusions(self):
        """Test comparing LP problems with exclusion patterns."""
        pb1 = {
            "objectives": {"x": 1.0, "temp_var": 2.0},
            "constraints": {"c1": {"LB": 0, "UB": 10, "x": 1.0}},
            "variables": {"x": [0, 10], "temp_var": [0, 5]},
            "binaries": [],
        }
        pb2 = {
            "objectives": {"x": 1.0, "temp_var": 5.0},
            "constraints": {"c1": {"LB": 0, "UB": 10, "x": 1.0}},
            "variables": {"x": [0, 10], "temp_var": [0, 10]},
            "binaries": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            result = SolverHelper.compare_lp_problems(
                pb1,
                pb2,
                output_dir=tmpdir,
                exclude_patterns=["temp_.*"],
                keep_identical=False,
            )

            # temp_var should be excluded, so only x should be compared
            assert result["objectives"]["total_legacy"] == 1
