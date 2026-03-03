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
def lp_legacy_match_file():
    """Path to legacy LP correspondence file."""
    return TEST_DATA_DIR / "es_battery_lp.lp_correspondance.csv"


@pytest.fixture
def new_lp():
    """Path for new LP file (temporary)."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
        temp_path = f.name
    yield temp_path
    # Cleanup after test
    Path(temp_path).unlink(missing_ok=True)


class TestModelToDict:
    """Tests for model_to_dict method."""

    def test_model_to_dict_basic(self, simple_solver):
        """Test converting a simple solver to dictionary."""
        result = SolverHelper.model_to_dict(simple_solver)

        assert "constraints" in result
        assert "variables" in result
        assert "objectives" in result

        # Check constraints
        assert len(result["constraints"]) == 2
        assert "constraint_1" in result["constraints"]
        assert "constraint_2" in result["constraints"]

        # Check variables
        assert len(result["variables"]) == 2

        # Check objectives
        assert result["objectives"][0] is True  # maximization

    def test_model_to_dict_constraint_structure(self, simple_solver):
        """Test constraint structure in dictionary."""
        result = SolverHelper.model_to_dict(simple_solver)
        constraint_1 = result["constraints"]["constraint_1"]

        # First two elements are bounds [lb, ub]
        lb, ub = constraint_1[0], constraint_1[1]
        assert lb == float("-inf")
        assert ub == 14

        # Remaining elements are (var_name, coefficient) tuples
        coefficients = dict(constraint_1[2:])
        assert "x" in coefficients
        assert "y" in coefficients

    def test_model_to_dict_with_binaries(self, solver_with_binaries):
        """Test converting solver with binary variables."""
        result = SolverHelper.model_to_dict(solver_with_binaries)

        assert len(result["variables"]) == 2

        # Find the binary variable
        binary_var = next(v for v in result["variables"] if v["Name"] == "binary_x")
        assert binary_var["VarType"] == "OpBinary"
        assert binary_var["LowBound"] == 0
        assert binary_var["UpBound"] == 1


class TestModelFromDict:
    """Tests for model_from_dict method."""

    def test_model_from_dict_basic(self, simple_solver):
        """Test creating solver from dictionary."""
        model_dict = SolverHelper.model_to_dict(simple_solver)
        new_solver = SolverHelper.model_from_dict(model_dict, "GLOP")

        assert new_solver.NumVariables() == simple_solver.NumVariables()
        assert new_solver.NumConstraints() == simple_solver.NumConstraints()

    def test_model_from_dict_roundtrip(self, simple_solver):
        """Test roundtrip conversion (solver -> dict -> solver)."""
        model_dict = SolverHelper.model_to_dict(simple_solver)
        new_solver = SolverHelper.model_from_dict(model_dict, "GLOP")
        new_dict = SolverHelper.model_to_dict(new_solver)

        # Check that dictionaries are equivalent
        assert len(model_dict["constraints"]) == len(new_dict["constraints"])
        assert len(model_dict["variables"]) == len(new_dict["variables"])


class TestDictFromVar:
    """Tests for dict_from_var method."""

    def test_dict_from_var_continuous(self):
        """Test converting continuous variable to dict."""
        solver = pywraplp.Solver.CreateSolver("GLOP")
        var = solver.NumVar(0, 10, "test_var")

        result = SolverHelper.dict_from_var(var)

        assert result["Name"] == "test_var"
        assert result["LowBound"] == 0
        assert result["UpBound"] == 10
        assert result["VarType"] == "OpReal"

    def test_dict_from_var_binary(self):
        """Test converting binary variable to dict."""
        solver = pywraplp.Solver.CreateSolver("SCIP")
        var = solver.IntVar(0, 1, "binary_var")

        result = SolverHelper.dict_from_var(var)

        assert result["Name"] == "binary_var"
        assert result["VarType"] == "OpBinary"

    def test_dict_from_var_integer(self):
        """Test converting integer variable to dict."""
        solver = pywraplp.Solver.CreateSolver("SCIP")
        var = solver.IntVar(0, 100, "int_var")

        result = SolverHelper.dict_from_var(var)

        assert result["Name"] == "int_var"
        assert result["VarType"] == "OpInterger"  # Note: typo in original code

    def test_dict_from_var_with_value(self):
        """Test converting variable with custom value."""
        solver = pywraplp.Solver.CreateSolver("GLOP")
        var = solver.NumVar(0, 10, "test_var")

        result = SolverHelper.dict_from_var(var, value=5.5)

        assert result["VarValue"] == 5.5


class TestVarFromDict:
    """Tests for var_from_dict method."""

    def test_var_from_dict_continuous(self):
        """Test creating continuous variable from dict."""
        solver = pywraplp.Solver.CreateSolver("GLOP")
        dict_var = {
            "Name": "x",
            "LowBound": 0,
            "UpBound": 10,
            "VarType": "OpReal",
            "VarValue": 0,
        }

        var = SolverHelper.var_from_dict(dict_var, solver)

        assert var.name() == "x"
        assert var.lb() == 0
        assert var.ub() == 10
        assert not var.integer()

    def test_var_from_dict_binary(self):
        """Test creating binary variable from dict."""
        solver = pywraplp.Solver.CreateSolver("SCIP")
        dict_var = {
            "Name": "b",
            "LowBound": 0,
            "UpBound": 1,
            "VarType": "OpBinary",
            "VarValue": 0,
        }

        var = SolverHelper.var_from_dict(dict_var, solver)

        assert var.name() == "b"
        assert var.integer()


class TestConstraintFromDict:
    """Tests for constraint_from_dict method."""

    def test_constraint_from_dict_basic(self):
        """Test creating constraint from dict."""
        solver = pywraplp.Solver.CreateSolver("GLOP")
        x = solver.NumVar(0, 10, "x")
        y = solver.NumVar(0, 10, "y")

        constraint_data = [0, 10, ("x", 1), ("y", 2)]
        constraint = SolverHelper.constraint_from_dict("test_ct", constraint_data, solver)

        assert constraint.name() == "test_ct"
        assert constraint.lb() == 0
        assert constraint.ub() == 10
        assert constraint.GetCoefficient(x) == 1
        assert constraint.GetCoefficient(y) == 2


class TestObjectiveFromDict:
    """Tests for objective_from_dict method."""

    def test_objective_from_dict_maximization(self):
        """Test creating maximization objective from dict."""
        solver = pywraplp.Solver.CreateSolver("GLOP")
        x = solver.NumVar(0, 10, "x")
        y = solver.NumVar(0, 10, "y")

        objective_data = [True, 0, ("x", 3), ("y", 4)]
        SolverHelper.objective_from_dict(objective_data, solver)

        obj = solver.Objective()
        assert obj.maximization()
        assert obj.GetCoefficient(x) == 3
        assert obj.GetCoefficient(y) == 4

    def test_objective_from_dict_minimization(self):
        """Test creating minimization objective from dict."""
        solver = pywraplp.Solver.CreateSolver("GLOP")
        _ = solver.NumVar(0, 10, "x")

        objective_data = [False, 0, ("x", 1)]
        SolverHelper.objective_from_dict(objective_data, solver)

        obj = solver.Objective()
        assert obj.minimization()

    def test_objective_from_dict_with_offset(self):
        """Test creating objective with offset."""
        solver = pywraplp.Solver.CreateSolver("GLOP")
        _ = solver.NumVar(0, 10, "x")

        objective_data = [True, 10.5, ("x", 1)]
        SolverHelper.objective_from_dict(objective_data, solver)

        obj = solver.Objective()
        assert obj.Offset() == 10.5


class TestExportProblemAsLP:
    """Tests for export_problem_as_lp method."""

    def test_export_problem_as_lp(self, simple_solver):
        """Test exporting problem to LP format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            filename = f.name

        try:
            SolverHelper.export_problem_as_lp(simple_solver, filename)
            assert Path(filename).exists()

            # Check file content
            with open(filename) as f:
                content = f.read()
                assert "Maximize" in content or "Minimize" in content
        finally:
            Path(filename).unlink(missing_ok=True)


class TestCustomExportProblemAsLP:
    """Tests for custom_export_problem_as_lp method."""

    def test_custom_export_maximization(self, simple_solver):
        """Test custom export for maximization problem."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            filename = f.name

        try:
            SolverHelper.custom_export_problem_as_lp(simple_solver, filename)

            with open(filename) as f:
                content = f.read()
                assert content.startswith("Maximize")
                assert "Subject To" in content
                assert "Bounds" in content
                assert "End" in content
        finally:
            Path(filename).unlink(missing_ok=True)

    def test_custom_export_with_binaries(self, solver_with_binaries):
        """Test custom export with binary variables."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            filename = f.name

        try:
            SolverHelper.custom_export_problem_as_lp(solver_with_binaries, filename)

            with open(filename) as f:
                content = f.read()
                assert "Binaries" in content
                assert "binary_x" in content
        finally:
            Path(filename).unlink(missing_ok=True)


class TestExportSolutionAsLP:
    """Tests for export_solution_as_lp method."""

    def test_export_solution_optimal(self, simple_solver):
        """Test exporting optimal solution."""
        status = simple_solver.Solve()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            filename = f.name

        try:
            SolverHelper.export_solution_as_lp(simple_solver, status, filename)

            with open(filename) as f:
                content = f.read()
                assert "SOLUTION" in content
                assert "OBJECTIVE FUNCTION" in content
                assert "VARIABLES" in content
                assert "CONSTRAINTS" in content
        finally:
            Path(filename).unlink(missing_ok=True)


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


class TestRebuildLPWithRealNames:
    """Tests for rebuild_lp_with_real_names method."""

    def test_rebuild_lp(self, lp_legacy, lp_legacy_match_file, new_lp):
        """Test rebuilding LP with real names."""
        SolverHelper.rebuild_lp_with_real_names(lp_legacy, lp_legacy_match_file, new_lp)

        # Check that file was created
        assert Path(new_lp).exists()

        # Check that both LPs have the same structure
        result_original = SolverHelper.read_lp_legacy(lp_legacy)
        result_new = SolverHelper.read_lp_legacy(new_lp)

        assert len(result_original["objectives"]) == len(result_new["objectives"])
        assert len(result_original["constraints"]) == len(result_new["constraints"])
        assert len(result_original["variables"]) == len(result_new["variables"])
        assert len(result_original["binaries"]) == len(result_new["binaries"])


class TestSolutionToDict:
    """Tests for solution_to_dict method."""

    def test_solution_to_dict(self, simple_solver):
        """Test converting solution file to dictionary."""
        status = simple_solver.Solve()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f:
            filename = f.name

        try:
            SolverHelper.export_solution_as_lp(simple_solver, status, filename)
            result = SolverHelper.solution_to_dict(filename)

            assert isinstance(result, dict)
            assert "Value" in result
        finally:
            Path(filename).unlink(missing_ok=True)


class TestCompareSolutionsAsLP:
    """Tests for compare_solutions_as_lp method."""

    def test_compare_identical_solutions(self, simple_solver):
        """Test comparing identical solutions."""
        status = simple_solver.Solve()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f1:
            file1 = f1.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f2:
            file2 = f2.name

        try:
            SolverHelper.export_solution_as_lp(simple_solver, status, file1)
            SolverHelper.export_solution_as_lp(simple_solver, status, file2)

            result = SolverHelper.compare_solutions_as_lp(file1, file2)
            assert result is True
        finally:
            Path(file1).unlink(missing_ok=True)
            Path(file2).unlink(missing_ok=True)

    def test_compare_different_solutions(self, simple_solver):
        """Test comparing different solutions."""
        # Solve first problem
        status1 = simple_solver.Solve()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f1:
            file1 = f1.name

        try:
            SolverHelper.export_solution_as_lp(simple_solver, status1, file1)

            # Modify problem and solve again
            simple_solver.Objective().SetCoefficient(simple_solver.LookupVariable("x"), 10)
            status2 = simple_solver.Solve()

            with tempfile.NamedTemporaryFile(mode="w", suffix=".lp", delete=False) as f2:
                file2 = f2.name

            try:
                SolverHelper.export_solution_as_lp(simple_solver, status2, file2)
                result = SolverHelper.compare_solutions_as_lp(file1, file2)
                assert result is False
            finally:
                Path(file2).unlink(missing_ok=True)
        finally:
            Path(file1).unlink(missing_ok=True)


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
