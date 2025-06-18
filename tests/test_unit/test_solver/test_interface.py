
import unittest

from atlas.solver.solver_interface import OptimisationModel
from atlas.enum import SolverStatus


class TestSolverInterface(unittest.TestCase):

    def setUp(self):
        """Setup test environment before each test"""
        self.model = OptimisationModel("GLOP", "unit_test_solver");

    def tearDown(self):
        """Clean up after each test"""
        self.model.clear()

    def set_up_simple_model(self):
        self.model.add_boolean_variable("x")
        self.model.add_boolean_variable("y")
        self.model.add_linear_constraint({"x": 1, "y": 1}, "<=", 1, "unit_test_constraint")
        self.model.set_objective({"x": 1, "y": 1.1})

    def test_add_continuous_variable(self):
        """Add a continuous variable and check if present"""
        self.model.add_continuous_variable("x1")
        assert "x1" in self.model.variables_name

        self.model.add_continuous_variable("x2", -float("inf"), 0.0)
        assert "x2" in self.model.variables_name

        self.model.add_continuous_variable("x3", 0.0, 0.0)
        assert "x3" in self.model.variables_name

        self.model.add_continuous_variable("x4", 0.0, float("inf"))
        assert "x4" in self.model.variables_name

        self.model.add_continuous_variable("x5", -float("inf"), float("inf"))
        assert "x5" in self.model.variables_name

    def test_add_multiple_continuous_variables(self):
        self.model.add_continuous_variables(["y1", "y2", "y3"])
        assert "y1" in self.model.variables_name
        assert "y2" in self.model.variables_name
        assert "y3" in self.model.variables_name

    def test_add_integer_variable(self):
        """Add an integer variable and check if present"""
        self.model.add_integer_variable("x1")
        assert "x1" in self.model.variables_name

        self.model.add_integer_variable("x2", -float("inf"), 0.0)
        assert "x2" in self.model.variables_name

        self.model.add_integer_variable("x3", 0.0, 0.0)
        assert "x3" in self.model.variables_name

        self.model.add_integer_variable("x4", 0.0, float("inf"))
        assert "x4" in self.model.variables_name

        self.model.add_integer_variable("x5", -float("inf"), float("inf"))
        assert "x5" in self.model.variables_name

    def test_add_bool_variable(self):
        """Add a boolean variable and check if present"""
        self.model.add_boolean_variable("x1")
        assert "x1" in self.model.variables_name

    def test_add_linear_constraint(self):
        """Add a simple constrainst and check if present"""
        self.model.add_integer_variable("x")
        self.model.add_continuous_variable("y")
        self.model.add_boolean_variable("z")
        self.model.add_linear_constraint(
            {"x": 1, "y": 2, "z": 1},
            "<=",
            3,
            "unit_test_constraint"
        )
        assert "unit_test_constraint" in self.model.constraints_name

    def test_set_objective(self):
        """Ensure that set objective works"""
        self.model.add_integer_variable("x")
        self.model.add_continuous_variable("y")
        self.model.add_boolean_variable("z")
        self.model.set_objective({"x": 1, "y": 2, "z": 1})
        assert len(self.model.objective) == 3
        assert self.model.objective["x"] == 1
        assert self.model.objective["y"] == 2
        assert self.model.objective["z"] == 1

    def test_set_objective_overwrite(self):
        """Ensure that set objective works"""
        self.model.add_integer_variable("x")
        self.model.set_objective({"x": 1})
        assert len(self.model.objective) == 1
        assert self.model.objective["x"] == 1

        self.model.add_continuous_variable("y")
        self.model.set_objective({"y": 2})
        assert len(self.model.objective) == 1
        assert self.model.objective["y"] == 2

    def test_set_add_objective(self):
        """Ensure that we can add criteria to the objective"""
        self.model.add_integer_variable("x")
        self.model.set_objective({"x": 1})
        assert len(self.model.objective) == 1
        assert self.model.objective["x"] == 1

        self.model.add_continuous_variable("y")
        self.model.add_boolean_variable("z")
        self.model.add_objective({"y": 2, "z": 1})
        assert len(self.model.objective) == 3
        assert self.model.objective["x"] == 1
        assert self.model.objective["y"] == 2
        assert self.model.objective["z"] == 1

    def test_write_small_model(self):
        """Ensure that we can build a simple model"""
        self.model.add_integer_variable("x")
        self.model.add_continuous_variable("y")
        self.model.add_boolean_variable("z")
        self.model.add_linear_constraint(
            {"x": 1, "y": 2, "z": 1},
            "<=",
            3,
            "unit_test_constraint"
        )
        self.model.set_objective({"x": 1, "y": 1, "z": 1})

        assert "x" in self.model.variables_name
        assert "y" in self.model.variables_name
        assert "z" in self.model.variables_name

        assert "unit_test_constraint" in self.model.constraints_name

        assert len(self.model.objective) == 3
        assert self.model.objective["x"] == 1
        assert self.model.objective["y"] == 1
        assert self.model.objective["z"] == 1

    def test_clear(self):
        """Ensure that we can build a simple model"""
        self.model.add_integer_variable("x")
        self.model.add_continuous_variable("y")
        self.model.add_boolean_variable("z")
        self.model.add_linear_constraint(
            {"x": 1, "y": 2, "z": 1},
            "<=",
            3,
            "unit_test_constraint"
        )
        self.model.set_objective({"x": 1, "y": 2, "z": 1})
        self.model.clear()

        assert "x" not in self.model.variables_name
        assert "y" not in self.model.variables_name
        assert "z" not in self.model.variables_name

        assert "unit_test_constraint" not in self.model.constraints_name

        assert self.model.objective is None

    def test_variable_name_unicity(self):
        """Ensure that we can't create 2 variables with the same name"""
        self.model.add_integer_variable("x")
        try:
            self.model.add_integer_variable("x")
        except ValueError:
            assert True
        else:
            assert False

    def test_constraint_name_unicity(self):
        """Ensure that we can't create 2 constraints with the same name"""

        self.model.add_integer_variable("x")
        self.model.add_linear_constraint({"x": 1}, "<=", 3, "unit_test_constraint")
        try:
            self.model.add_linear_constraint({"x": 1}, "<=", 3, "unit_test_constraint")
        except ValueError:
            assert True
        else:
            assert False

    def test_get_variable_value(self):
        self.model.add_integer_variable("x")
        self.model.add_linear_constraint(
            {"x": 1}, "<=", 1, "unit_test_constraint")
        self.model.set_objective({"x": 1})
        self.model.solve()
        assert self.model.get_variable_value("x") == 1

    def test_get_variable_value_with_unsolved_model(self):
        self.model.add_integer_variable("x")
        try:
            self.model.get_variable_value("x")
        except RuntimeError:
            assert True
        else:
            assert False

    def test_get_undeclared_variable_value(self):
        self.model.solve()
        try:
            self.model.get_variable_value("x")
        except ValueError:
            assert True
        else:
            assert False

    def test_solve_empty_model(self):
        """Solve an empty model"""
        solution_info = self.model.solve()
        assert solution_info.objective_value == 0.0
        assert solution_info.status == SolverStatus.OPTIMAL

    def test_solve_model(self):
        """Ensure that we can solve the model"""
        self.set_up_simple_model()
        solution_info = self.model.solve()
        assert solution_info.objective_value == 1.1
        assert solution_info.status == SolverStatus.OPTIMAL

    def test_solve_infeasible_model(self):
        """Ensure that we can solve the model"""
        self.set_up_simple_model()
        self.model.add_linear_constraint({"x": 1}, "<=", -1, "infeasible_constraint")
        solution_info = self.model.solve()
        assert solution_info.objective_value is None
        assert solution_info.status == SolverStatus.INFEASIBLE

    def test_export_model(self):
        """Ensure that we can export the model"""
        self.set_up_simple_model()
        self.model.solve()
        # FIXME check that file exist and contains expected data
        self.model.export_model("this_is_a_lp_file.lp")

    def test_get_variable_value(self):
        """Ensure that we can retrieve variables value"""
        self.set_up_simple_model()
        self.model.solve()
        assert self.model.get_variable_value("x") == 0
        assert self.model.get_variable_value("y") == 1

    def test_solution_info(self):
        """Check that the solution info return after solving is valid"""
        self.set_up_simple_model()
        info = self.model.solve()
        assert info.status == SolverStatus.OPTIMAL
        assert info.objective_value == 1.1
