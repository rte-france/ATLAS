"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import re
from collections import OrderedDict
from pathlib import Path

from ortools.linear_solver import pywraplp


class SolverHelper:
    """This class implements utility methods for OrTools linear Solver and Variables."""

    SOLVED_STATUS = [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]

    @staticmethod
    def model_to_dict(solver):
        """
        Transform a Solver object to a dict

        :param solver: ortools.linear_solver.pywraplp.Solver. The solver to transform.
        :return: dict(str, 2d array)
        """
        model_dict = {"constraints": {}}
        for cstr in solver.constraints():
            constraint = solver.LookupConstraint(cstr.name())
            constraint_name = cstr.name().replace(" ", "_").replace("-", "_").replace(":", "_")
            model_dict["constraints"][constraint_name] = [constraint.lb(), constraint.ub()] + [
                (var.name(), constraint.GetCoefficient(var))
                for var in solver.variables()
                if abs(constraint.GetCoefficient(var)) > 1e-8
            ]
        model_dict["variables"] = []
        for variable in solver.variables():
            model_dict["variables"].append(SolverHelper.dict_from_var(variable))
        objective = solver.Objective()
        model_dict["objectives"] = [objective.maximization(), objective.Offset()] + [
            (var.name(), objective.GetCoefficient(var))
            for var in solver.variables()
            if abs(objective.GetCoefficient(var)) > 1e-8
        ]
        return model_dict

    @staticmethod
    def custom_export_problem_as_lp(solver, filename):
        """
        Export solver problem to lp with a custom format in order to keep float consistency

        :param solver: ortools.linear_solver.pywraplp.Solver. The solver to transform.
        :param filename: str or os.PathLike. File where lp will be saved.
        :return
        """
        json_model = SolverHelper.model_to_dict(solver)
        lp_string = "Maximize" if json_model["objectives"][0] else "Minimize"
        lp_string += "\n OBJ: "
        if abs(json_model["objectives"][1]) > 0.0:
            lp_string += str(json_model["objectives"][1])
        for name, coeff in json_model["objectives"][2:]:
            # lp_string += " +" if coeff > 0.0 else " "
            # lp_string += str(coeff) + " " + name
            if coeff > 0.0:
                lp_string += " +" + str(coeff) + " " + name
            elif coeff < 0.0:
                lp_string += " " + str(coeff) + " " + name

        lp_string += "\nSubject To"
        for constraint_name, constraint in json_model["constraints"].items():
            lp_string += "\n " + str(constraint_name) + ":"
            for name, coeff in constraint[2:]:
                # lp_string += " +" if coeff > 0.0 else " "
                # lp_string += str(coeff) + " " + name
                if coeff > 0.0:
                    lp_string += " +" + str(coeff) + " " + name
                elif coeff < 0.0:
                    lp_string += " " + str(coeff) + " " + name
            lb, ub = constraint[0], constraint[1]
            if lb == ub:
                lp_string += " = " + str(lb)
            else:
                if abs(lb) == float("inf"):
                    lp_string += " <= " + str(ub)
                else:
                    lp_string += " >= " + str(lb)

        lp_string += "\nBounds"
        for var_dict in json_model["variables"]:
            if "OpBinary" not in var_dict["VarType"] and "OpInteger" not in var_dict["VarType"]:
                if abs(var_dict["LowBound"]) == abs(var_dict["UpBound"]) == float("inf"):
                    lp_string += "\n " + var_dict["Name"] + " free"
                else:
                    lp_string += (
                        "\n "
                        + str(var_dict["LowBound"])
                        + " <= "
                        + var_dict["Name"]
                        + " <= "
                        + str(var_dict["UpBound"])
                    )

        lp_string += "\nBinaries"
        for var_dict in json_model["variables"]:
            if "OpBinary" in var_dict["VarType"]:
                lp_string += "\n " + var_dict["Name"]
        lp_string += "\nEnd"
        with open(filename, "w") as f:
            f.write(lp_string)

    @staticmethod
    def model_from_dict(model_dict, solver_name):
        """
        Transform a dict to a Solver object

        :param model_dict: dict(str, 2d array). Dict representing the solver to create
        :param solver_name: str. Name of the solver to create
        :return: ortools.linear_solver.pywraplp.Solver.
        """
        solver = pywraplp.Solver.CreateSolver(solver_name)
        for variable in model_dict["variables"]:
            SolverHelper.var_from_dict(variable, solver)
        for ct_name, ct_parameters in model_dict["constraints"].items():
            SolverHelper.constraint_from_dict(ct_name, ct_parameters, solver)
        SolverHelper.objective_from_dict(model_dict["objectives"], solver)

        return solver

    @staticmethod
    def model_from_dict_mc(model_dict, solver_name):
        """
        Transform a dict to a Solver object

        :param model_dict: dict(str, 2d array). Dict representing the solver to create
        :param solver_name: str. Name of the solver to create
        :return: ortools.linear_solver.pywraplp.Solver.
        """
        solver = pywraplp.Solver.CreateSolver(solver_name)
        for name, variable_dict in sorted(model_dict["variables"].items()):
            SolverHelper.var_from_dict_mc(
                name, variable_dict, True if name in model_dict["binaries"] else False, solver
            )
        for binary_name in sorted(model_dict["binaries"]):
            if not solver.LookupVariable(binary_name):
                solver.IntVar(0, 1, binary_name)
        for ct_name, ct_parameters in sorted(model_dict["constraints"].items()):
            SolverHelper.constraint_from_dict_mc(ct_name, ct_parameters, solver)
        SolverHelper.objective_from_dict_mc(model_dict["objectives"], solver)

        return solver

    @staticmethod
    def constraint_from_dict(name, constraint, solver):
        """
        Create a ortools Constraint in a solver with a name and a list input

        :param name: str. TName of the constraint.
        :param constraint: 2d array. List containing all information for a constraint
            [lower bound, upper bound, (variable name, coefficient), ...].
        :param solver: ortools.linear_solver.pywraplp.Solver. THe solver where to add the constraint.
        :return
        """
        lb = constraint[0]
        ub = constraint[1]
        ct = solver.Constraint(lb, ub, name)
        for var_name, coeff in constraint[2:]:
            ct.SetCoefficient(solver.LookupVariable(var_name), coeff)
        return ct

    @staticmethod
    def constraint_from_dict_mc(name, constraint, solver):
        """
        Create a ortools Constraint in a solver with a name and a list input

        :param name: str. TName of the constraint.
        :param constraint: 2d array. List containing all information for a constraint
            [lower bound, upper bound, (variable name, coefficient), ...].
        :param solver: ortools.linear_solver.pywraplp.Solver. THe solver where to add the constraint.
        :return
        """
        lb = constraint["LB"]
        ub = constraint["UB"]
        ct = solver.Constraint(lb, ub, name)
        for var_name, coeff in sorted(constraint.items()):
            if var_name in ["LB", "UB"]:
                continue
            ct.SetCoefficient(solver.LookupVariable(var_name), coeff)
        return ct

    @staticmethod
    def objective_from_dict_mc(objective, solver):
        """
        Create the objective in a solver with list input

        :param objective: 2d array. List containing all information for a constraint
            [direction of the optimization, offset, (variable name, coefficient), ...].
        :param solver: ortools.linear_solver.pywraplp.Solver. THe solver where to add the objective.
        :return
        """
        obj = solver.Objective()
        constant = objective.get("Constant")
        if constant:
            obj.SetOffset(constant)
        for var_name, coeff in sorted(objective.items()):
            if var_name == "Constant":
                continue
            obj.SetCoefficient(solver.LookupVariable(var_name), coeff)
        obj.SetOptimizationDirection(True)

    @staticmethod
    def objective_from_dict(objective, solver):
        """
        Create the objective in a solver with list input

        :param objective: 2d array. List containing all information for a constraint
            [direction of the optimization, offset, (variable name, coefficient), ...].
        :param solver: ortools.linear_solver.pywraplp.Solver. THe solver where to add the objective.
        :return
        """
        obj = solver.Objective()
        obj.SetOffset(objective[1])
        for var_name, coeff in objective[2:]:
            obj.SetCoefficient(solver.LookupVariable(var_name), coeff)
        obj.SetOptimizationDirection(objective[0])

    @staticmethod
    def var_from_dict_mc(name, var, boolean, solver):
        lb = var[0]
        ub = var[1]

        if boolean:
            var = solver.IntVar(lb, ub, name)
        else:
            var = solver.NumVar(lb, ub, name)
        return var

    @staticmethod
    def var_from_dict(dict_var, solver):
        """
        Convert a dict representation of an optimisation variable to an OrTools variable and add it to the given solver

        :param dict_var: dict. Representation of an optimisation variable
        :param solver: ortools.linear_solver.pywraplp.Solver. The solver associated to the new variable
        :return: OrTools variable
        """
        var_type = dict_var["VarType"]
        lb = dict_var["LowBound"]
        ub = dict_var["UpBound"]
        name = dict_var["Name"]

        if var_type in ["OpBinary", "OpInteger"]:
            var = solver.IntVar(lb, ub, name)
        else:
            var = solver.NumVar(lb, ub, name)
        return var

    @staticmethod
    def dict_from_var(var, value=None):
        """
        Convert an OrTools variable to a dict representation

        :param var: OrTools variable. The variable to be converted
        :param value: float. Optional value of the variable to set
        :return: dict representation of the variable
        """
        if var.integer():
            if var.lb() == 0 and var.ub() == 1:
                var_type = "OpBinary"
            else:
                var_type = "OpInterger"
        else:
            var_type = "OpReal"
        return {
            "Name": var.name(),
            "LowBound": var.lb(),
            "UpBound": var.ub(),
            "VarValue": value if value is not None else var.solution_value(),
            "VarType": var_type,
        }

    @staticmethod
    def export_solution_as_lp(solver, status, filename):
        """
        Export the solution in lp format to a file

        :param solver: Solver. The solver from which we want to export the solution
        :param status: int. Status of the solver
        :param filename: str or os.PathLike. Path where the lp solution will be saved
        :return:
        """
        with open(filename, "w") as f:
            f.write("--------------------------- INFO ----------------------------\n")
            objective = solver.Objective()
            f.write(f"Sens : {'Minimization' if objective.minimization() else 'Maximization'}\n")
            f.write("------------------------- SOLUTION --------------------------\n")
            f.write("Status : \n")
            f.write("--------------------- OBJECTIVE FUNCTION --------------------\n")
            objective_value = objective.Value() if status in SolverHelper.SOLVED_STATUS else 0
            f.write(f"Value: {objective_value:.6f}\n")
            f.write("-------------------- CONSTRAINTS (MARGINAL COST) --------------------\n")
            for constraint in sorted(solver.constraints(), key=lambda x: x.name()):
                f.write(f"{constraint.name()} = {0:.6f}\n")
            f.write("------------------------- VARIABLES -------------------------\n")
            for variable in sorted(solver.variables(), key=lambda x: x.name()):
                variable_solution = variable.solution_value() if status in SolverHelper.SOLVED_STATUS else 0
                f.write(f"{variable.name()} = {variable_solution:.6f}\n")

    @staticmethod
    def get_constraint_value(solver, constraint_name):
        """
        Get the value of the constraint given (AffineExpression)

        :param solver: solver
        :param constraint_name: the constraint name
        :return: the value of constraint
        """
        constraint = solver.LookupConstraint(constraint_name)
        sum_coefs = sum([constraint.GetCoefficient(var) * var.solution_value() for var in solver.variables()])
        return sum_coefs - constraint.ub() if constraint.ub() != float("inf") else sum_coefs - constraint.lb()

    @staticmethod
    def compare_solutions_as_lp(filename1, filename2, tolerance=1e-6, absolute_tolerance=1e-12):
        """
        Check that the solutions of two problems in lp format are identical

        :param filename1: str or os.PathLike. Path to the first solution.lp file
        :param filename2: str or os.PathLike. Path to the second solution.lp file
        :param tolerance: float. Relative error tolerance.
        :param absolute_tolerance: float. Absolute error tolerance
        :return: True if solutions are identical, False otherwise
        """
        solution1 = SolverHelper.solution_to_dict(filename1)
        solution2 = SolverHelper.solution_to_dict(filename2)

        # Check if all keys are present in both solutions
        all_keys = set(solution1.keys()) | set(solution2.keys())

        for key in all_keys:
            val1 = solution1.get(key, 0.0)
            val2 = solution2.get(key, 0.0)

            # Check if values are identical within tolerance
            if abs(val1 - val2) > max(tolerance * max(abs(val1), abs(val2)), absolute_tolerance):
                return False

        return True

    @staticmethod
    def solution_to_dict(solution_file):
        """
        Convert a txt solution file to a dict with keys corresponding to variable, constraint or solution name and
        values corresponding to their values

        :param solution_file: str or os.PathLike. Path to the solution.lp file
        :return: dict
        """
        solution = {}
        with open(solution_file) as file:
            lines = file.readlines()
        for line in lines:
            line = line.strip()
            line = line.replace(" ", "")
            # Get solution value
            if "Value" in line:
                key, value = line.split(":")
                solution[key] = float(value)
            elif "=" in line:
                key, value = line.split("=")
                solution[key] = float(value)

        return solution

    @staticmethod
    def export_problem_as_lp(solver, filename):
        """
        Export the problem in lp format to a file

        :param solver: Solver. The solver from which we want to export the solution
        :param filename: str or os.PathLike. Path where the lp problem will be saved
        :return:
        """
        with open(filename, "w") as f:
            f.write(solver.ExportModelAsLpFormat(False))

    @staticmethod
    def deactivate_constraint(constraint):
        """
        Deactivate a constraint by setting its bounds to (-inf, +inf)

        :param constraint: OrTools Constraint. The constraint  to deactivate
        :return: The deactivated constraint
        """
        if constraint is None:
            return
        constraint.SetBounds(float("-inf"), float("inf"))
        return constraint

    @staticmethod
    def read_lp_ortools(filepath):
        """
        Read a lp file generated by or-tools

        :param filepath: str or os.PathLike. File path of the lp problem generated by OrTools
        :return: dict containing objective function, constraints and variables definitions.
        """
        objectives = OrderedDict()
        constraints = OrderedDict()
        variables = OrderedDict()
        binaries = []
        section = None
        prev_line = ""
        with open(filepath) as file:
            lines = file.readlines()
        for id_line, line in enumerate(lines):
            line = line.strip()
            line = prev_line + line

            prev_line = ""
            current_line = line
            if line.startswith("Obj: "):
                section = "obj"
                line = line.replace("Obj: ", "")
            if section == "obj":
                if lines[id_line + 1].startswith("Subject to"):
                    line = line.split(" ")
                    for idx in range(0, len(line), 2):
                        coef, var = line[idx : idx + 2]
                        objectives[var] = float(coef)
                    continue
                elif line.startswith("Subject to"):
                    section = "constraint"
                    continue
                else:
                    prev_line = line + " "
                    continue

            elif line.startswith("Subject to"):
                section = "constraint"
            elif line.startswith("Bounds"):
                section = "variable"
                continue
            elif line.startswith("End"):
                break
            elif section == "constraint":
                constraint_name, line = line.split(": ")
                if ">=" in line:
                    line, lb = line.split(" >= ")
                    ub = float("inf")
                elif "<=" in line:
                    line, ub = line.split(" <= ")
                    lb = float("-inf")
                elif "=" in line:
                    line, bound = line.split(" = ")
                    lb, ub = bound, bound
                else:
                    prev_line = current_line + " "
                    continue

                    # raise ValueError("Constraint line must contain >=, <=, or = sign")
                line = line.split(" ")
                if "" in line:
                    line.remove("")
                constraint = OrderedDict()
                for idx in range(0, len(line), 2):
                    coef, var_name = line[idx : idx + 2]
                    constraint[var_name] = float(coef)
                constraint["LB"] = float(lb)
                constraint["UB"] = float(ub)
                constraints[constraint_name] = constraint
            elif section == "variable":
                if line.startswith("Binaries"):
                    section = "binary"
                    continue
                if line.endswith("free"):
                    line = line.split(" ")
                    var_name, _ = line
                    variables[var_name] = [float("-inf"), float("inf")]
                else:
                    line = line.split(" <= ")
                    # Case where only on lb constraint
                    try:
                        if len(line) == 2:
                            lb, var_name = line
                            ub = "inf"
                        else:
                            lb, var_name, ub = line
                        variables[var_name] = [float(lb), float(ub)]
                    except:  # noqa: E722
                        if len(line) == 2:
                            var_name, ub = line
                            lb = "-inf"
                        else:
                            lb, var_name, ub = line
                        variables[var_name] = [float(lb), float(ub)]

            elif section == "binary":
                var_name = line
                binaries.append(var_name)
                # Add binary variables to variables dictionary if not already present
                if var_name not in variables:
                    variables[var_name] = [0.0, 1.0]  # Binary variables have bounds [0, 1]

        return {"objectives": objectives, "constraints": constraints, "variables": variables, "binaries": binaries}

    @staticmethod
    def read_lp_legacy(filepath):
        """
        Read a lp file

        :param filepath: str or os.PathLike. File path of the lp problem
        :return: dict containing objective function, constraints and variables definitions.
        """
        objectives = OrderedDict()
        constraints = OrderedDict()
        variables = OrderedDict()
        binaries = []
        section = None
        prev_line = ""
        with open(filepath) as file:
            lines = file.readlines()
        for line in lines:
            line = line.strip()
            line = prev_line + line
            current_line = line
            prev_line = ""
            if line.startswith("OBJ: "):
                line = line.replace("OBJ: ", "")
                # Remove spaces between signs and numerical values
                import re

                line = re.sub(r"([+\-*/])\s+(?=\d)", r"\1", line)
                line = re.sub(r"(?<=-)(?=[a-zA-Z])", " ", line)
                # line = line.replace("- ", "-")
                # line = line.replace("+ ", "+")
                line = line.split(" ")
                while "" in line:
                    line.remove("")

                for idx in range(0, len(line), 2):
                    # Constant of the objective function
                    if idx == len(line) - 1:
                        objectives["Constant"] = float(line[idx])
                        continue
                    coef, var = line[idx : idx + 2]
                    if coef == "-":
                        coef = "-1"
                    if coef == "+":
                        coef = "1"
                    objectives[var] = float(coef)
            elif line.startswith("Subject To"):
                section = "constraint"
            elif line.startswith("Bounds"):
                section = "variable"
                continue
            elif line.startswith("Binaries"):
                section = "binary"
                continue
            elif line.startswith("End"):
                break
            elif section == "constraint":
                constraint_name, line = line.split(": ")
                # Replace spaces by underscores in constraint names
                constraint_name = constraint_name.replace(" ", "_")
                # line = line.replace("- ", "-")
                # line = line.replace("+ ", "+")
                import re

                line = re.sub(r"([+\-*/])\s+(?=\d)", r"\1", line)
                if ">=" in line:
                    line, lb = line.split(">= ")
                    ub = float("inf")
                elif "<=" in line:
                    line, ub = line.split("<= ")
                    lb = float("-inf")
                elif "=" in line:
                    line, bound = line.split("= ")
                    lb, ub = bound, bound
                else:
                    prev_line = current_line + " "
                    continue

                    # raise ValueError("Constraint line must contain >=, <=, or = sign")
                line = line.strip().split(" ")

                if not SolverHelper.isfloat(line[0]) and line[0] not in ("+", "-"):
                    line.insert(0, "+")
                while "" in line:
                    line.remove("")
                if len(line) < 2:
                    line = []
                constraint = OrderedDict()
                for idx in range(0, len(line), 2):
                    coef, var_name = line[idx : idx + 2]
                    if coef == "-":
                        coef = "-1"
                    if coef == "+":
                        coef = "1"
                    constraint[var_name] = float(coef)
                constraint["LB"] = float(lb)
                constraint["UB"] = float(ub)
                constraints[constraint_name] = constraint
            elif section == "variable":
                if line.startswith("Binaries"):
                    section = "binary"
                    continue
                if line.endswith("free"):
                    line = line.split(" ")
                    var_name, _ = line
                    variables[var_name] = [float("-inf"), float("inf")]
                else:
                    line = line.split(" <= ")
                    if len(line) == 2:
                        var_name, ub = line
                        lb = 0
                    else:
                        lb, var_name, ub = line
                    variables[var_name] = [float(lb), float(ub)]

            elif section == "binary":
                var_name = line.strip()
                if var_name:  # Only add non-empty variable names
                    binaries.append(var_name)
                    # Add binary variables to variables dictionary if not already present
                    if var_name not in variables:
                        variables[var_name] = [0.0, 1.0]  # Binary variables have bounds [0, 1]

        return {"objectives": objectives, "constraints": constraints, "variables": variables, "binaries": binaries}

    @staticmethod
    def read_lp_custom(filepath):
        """
        Read a lp file generated by export_custom_lp

        :param filepath: str or os.PathLike. File path of the lp problem generated by export custom lp
        :return: dict containing objective function, constraints and variables definitions.
        """
        objectives = OrderedDict()
        constraints = OrderedDict()
        variables = OrderedDict()
        binaries = []
        section = None
        prev_line = ""
        with open(filepath) as file:
            lines = file.readlines()
        for line in lines:
            line = line.strip()
            line = prev_line + line
            current_line = line
            prev_line = ""
            if line.startswith("Obj: "):
                line = line.replace("Obj: ", "")
                line = line.replace("- ", "-")
                line = line.replace("+ ", "+")
                line = line.split(" ")
                while "" in line:
                    line.remove("")

                for idx in range(0, len(line), 2):
                    coef, var = line[idx : idx + 2]
                    objectives[var] = float(coef)
            elif line.startswith("Subject to"):
                section = "constraint"
            elif line.startswith("Bounds"):
                section = "variable"
                continue
            elif line.startswith("End"):
                break
            elif section == "constraint":
                constraint_name, line = line.split(": ")
                # Replace spaces by underscores in constraint names
                constraint_name = constraint_name.replace(" ", "_")
                # line = line.replace("- ", "-")
                # line = line.replace("+ ", "+")
                import re

                line = re.sub(r"([+\-*/])\s+(?=\d)", r"\1", line)
                if ">=" in line:
                    line, lb = line.split(">= ")
                    ub = float("inf")
                elif "<=" in line:
                    line, ub = line.split("<= ")
                    lb = float("-inf")
                elif "=" in line:
                    line, bound = line.split("= ")
                    lb, ub = bound, bound
                else:
                    prev_line = current_line + " "
                    continue

                    # raise ValueError("Constraint line must contain >=, <=, or = sign")
                line = line.split(" ")
                if not SolverHelper.isfloat(line[0]) and line[0] not in ("+", "-"):
                    line.insert(0, "+")
                while "" in line:
                    line.remove("")
                if len(line) < 2:
                    line = []
                constraint = OrderedDict()
                for idx in range(0, len(line), 2):
                    coef, var_name = line[idx : idx + 2]
                    if coef == "-":
                        coef = "-1"
                    if coef == "+":
                        coef = "1"
                    constraint[var_name] = float(coef)
                constraint["LB"] = float(lb)
                constraint["UB"] = float(ub)
                constraints[constraint_name] = constraint
            elif section == "variable":
                if line.startswith("Binaries"):
                    section = "binary"
                    continue
                if line.endswith("free"):
                    line = line.split(" ")
                    var_name, _ = line
                    variables[var_name] = [float("-inf"), float("inf")]
                else:
                    line = line.split(" <= ")
                    if len(line) == 2:
                        var_name, ub = line
                        lb = 0
                    else:
                        lb, var_name, ub = line
                    variables[var_name] = [float(lb), float(ub)]

            elif section == "binary":
                var_name = line
                binaries.append(var_name)
                # Add binary variables to variables dictionary if not already present
                if var_name not in variables:
                    variables[var_name] = [0.0, 1.0]  # Binary variables have bounds [0, 1]

        return objectives, constraints, variables, binaries

    @staticmethod
    def add_binaries_to_lp_problems_variables(lp_problem):
        for binary in lp_problem["binaries"]:
            if binary not in lp_problem["variables"]:
                lp_problem["variables"][binary] = [0.0, 1.0]

    @staticmethod
    def export_objective_differences_csv(
        pb1,
        pb2,
        filename,
        pb1_name="Before",
        pb2_name="After",
        tolerance=1e-5,
        normalize_names=True,
        keep_identical=True,
    ):
        """
        Export objective function differences to CSV

        :param pb1: dict. First LP problem (from read_lp_* methods)
        :param pb2: dict. Second LP problem (from read_lp_* methods)
        :param filename: str or Path. CSV file to save
        :param pb1_name: str. Name for first problem column
        :param pb2_name: str. Name for second problem column
        :param tolerance: float. Tolerance for numerical comparisons
        :param normalize_names: bool. Whether to normalize variable names (remove trailing colons, etc.)
        :param keep_identical: bool. Whether to keep rows with "Identical" status in the output
        """
        obj1 = pb1["objectives"]
        obj2 = pb2["objectives"]

        # Normalize variable names if requested
        if normalize_names:
            obj1_normalized = {}
            obj2_normalized = {}

            for var_name, coeff in obj1.items():
                normalized_name = SolverHelper.normalize_variable_name(var_name)
                if normalized_name in obj1_normalized:
                    print(f"Warning: Duplicate normalized objective variable '{normalized_name}' from '{var_name}'")
                obj1_normalized[normalized_name] = coeff

            for var_name, coeff in obj2.items():
                normalized_name = SolverHelper.normalize_variable_name(var_name)
                if normalized_name in obj2_normalized:
                    print(f"Warning: Duplicate normalized objective variable '{normalized_name}' from '{var_name}'")
                obj2_normalized[normalized_name] = coeff

            obj1 = obj1_normalized
            obj2 = obj2_normalized

        all_vars = set(obj1.keys()) | set(obj2.keys())

        with open(filename, "w") as f:
            f.write(f"Variable,{pb1_name}_Coefficient,{pb2_name}_Coefficient,Difference,Status\n")

            for var in sorted(all_vars):
                coeff1 = obj1.get(var, 0.0)
                coeff2 = obj2.get(var, 0.0)
                diff = coeff2 - coeff1

                if var not in obj1:
                    status = f"Only in {pb2_name}"
                elif var not in obj2:
                    status = f"Only in {pb1_name}"
                elif abs(diff) > tolerance:
                    status = "Modified"
                else:
                    status = "Identical"

                # Skip identical rows if keep_identical is False
                if not keep_identical and status == "Identical":
                    continue

                f.write(f"{var},{coeff1},{coeff2},{diff},{status}\n")

    @staticmethod
    def normalize_variable_name(var_name):
        """
        Normalize variable names by removing trailing colons and other formatting artifacts

        :param var_name: str. Variable name to normalize
        :return: str. Normalized variable name
        """
        return var_name.rstrip(":").strip()

    @staticmethod
    def export_variable_differences_csv(
        pb1,
        pb2,
        filename,
        pb1_name="Before",
        pb2_name="After",
        tolerance=1e-5,
        normalize_names=True,
        keep_identical=True,
    ):
        """
        Export variable bounds differences to CSV

        :param pb1: dict. First LP problem (from read_lp_* methods)
        :param pb2: dict. Second LP problem (from read_lp_* methods)
        :param filename: str or Path. CSV file to save
        :param pb1_name: str. Name for first problem column
        :param pb2_name: str. Name for second problem column
        :param tolerance: float. Tolerance for numerical comparisons
        :param normalize_names: bool. Whether to normalize variable names (remove trailing colons, etc.)
        :param keep_identical: bool. Whether to keep rows with "Identical" status in the output
        """
        vars1 = pb1["variables"]
        vars2 = pb2["variables"]

        # Normalize variable names if requested
        if normalize_names:
            # Create mapping of normalized names to original bounds
            vars1_normalized = {}
            vars2_normalized = {}

            for var_name, bounds in vars1.items():
                normalized_name = SolverHelper.normalize_variable_name(var_name)
                if normalized_name in vars1_normalized:
                    print(f"Warning: Duplicate normalized variable name '{normalized_name}' from '{var_name}'")
                vars1_normalized[normalized_name] = bounds

            for var_name, bounds in vars2.items():
                normalized_name = SolverHelper.normalize_variable_name(var_name)
                if normalized_name in vars2_normalized:
                    print(f"Warning: Duplicate normalized variable name '{normalized_name}' from '{var_name}'")
                vars2_normalized[normalized_name] = bounds

            vars1 = vars1_normalized
            vars2 = vars2_normalized

        all_vars = set(vars1.keys()) | set(vars2.keys())

        with open(filename, "w") as f:
            f.write(f"Variable,{pb1_name}_LB,{pb1_name}_UB,{pb2_name}_LB,{pb2_name}_UB,Status\n")

            for var in sorted(all_vars):
                if var in vars1:
                    lb1, ub1 = vars1[var]
                else:
                    lb1, ub1 = None, None

                if var in vars2:
                    lb2, ub2 = vars2[var]
                else:
                    lb2, ub2 = None, None

                if var not in vars1:
                    status = f"Only in {pb2_name}"
                elif var not in vars2:
                    status = f"Only in {pb1_name}"
                elif (abs(lb1 - lb2) > tolerance if lb1 is not None and lb2 is not None else lb1 != lb2) or (
                    abs(ub1 - ub2) > tolerance if ub1 is not None and ub2 is not None else ub1 != ub2
                ):
                    status = "Modified"
                else:
                    status = "Identical"

                # Skip identical rows if keep_identical is False
                if not keep_identical and status == "Identical":
                    continue

                f.write(f"{var},{lb1},{ub1},{lb2},{ub2},{status}\n")

    @staticmethod
    def export_constraint_differences_csv(
        pb1,
        pb2,
        filename,
        pb1_name="Before",
        pb2_name="After",
        tolerance=1e-5,
        normalize_names=True,
        keep_identical=True,
    ):
        """
        Export constraint differences to CSV

        :param pb1: dict. First LP problem (from read_lp_* methods)
        :param pb2: dict. Second LP problem (from read_lp_* methods)
        :param filename: str or Path. CSV file to save
        :param pb1_name: str. Name for first problem column
        :param pb2_name: str. Name for second problem column
        :param tolerance: float. Tolerance for numerical comparisons
        :param normalize_names: bool. Whether to normalize constraint names (remove trailing colons, etc.)
        :param keep_identical: bool. Whether to keep rows with "Identical" status in the output
        """
        constraints1 = pb1["constraints"]
        constraints2 = pb2["constraints"]

        # Normalize constraint names if requested
        if normalize_names:
            constraints1_normalized = {}
            constraints2_normalized = {}

            for constraint_name, constraint_data in constraints1.items():
                normalized_name = SolverHelper.normalize_variable_name(constraint_name)
                if normalized_name in constraints1_normalized:
                    print(f"Warning: Duplicate normalized constraint name '{normalized_name}' from '{constraint_name}'")
                constraints1_normalized[normalized_name] = constraint_data

            for constraint_name, constraint_data in constraints2.items():
                normalized_name = SolverHelper.normalize_variable_name(constraint_name)
                if normalized_name in constraints2_normalized:
                    print(f"Warning: Duplicate normalized constraint name '{normalized_name}' from '{constraint_name}'")
                constraints2_normalized[normalized_name] = constraint_data

            constraints1 = constraints1_normalized
            constraints2 = constraints2_normalized

        # Filter constraints (keep only those with variables)
        _constraints1 = {}
        _constraints2 = {}

        for k, v in constraints1.items():
            if isinstance(v, dict):
                # Dict format: check if it has variables (more than just LB/UB)
                if len(v) > 2 or any(key not in ["LB", "UB"] for key in v.keys()):
                    _constraints1[k] = v
            elif isinstance(v, list | tuple):
                # List format: check if it has more than 2 elements (LB, UB, variables...)
                if len(v) > 2:
                    _constraints1[k] = v

        for k, v in constraints2.items():
            if isinstance(v, dict):
                # Dict format: check if it has variables (more than just LB/UB)
                if len(v) > 2 or any(key not in ["LB", "UB"] for key in v.keys()):
                    _constraints2[k] = v
            elif isinstance(v, list | tuple):
                # List format: check if it has more than 2 elements (LB, UB, variables...)
                if len(v) > 2:
                    _constraints2[k] = v

        all_constraints = set(_constraints1.keys()) | set(_constraints2.keys())

        with open(filename, "w") as f:
            f.write(f"Constraint,{pb1_name}_LB,{pb1_name}_UB,{pb2_name}_LB,{pb2_name}_UB,Status\n")

            for constraint_name in sorted(all_constraints):
                if constraint_name in _constraints1:
                    c1 = _constraints1[constraint_name]
                    # Handle different constraint formats
                    if isinstance(c1, dict):
                        lb1, ub1 = c1.get("LB"), c1.get("UB")
                    elif isinstance(c1, list | tuple) and len(c1) >= 2:
                        lb1, ub1 = c1[0], c1[1]
                    else:
                        lb1, ub1 = None, None
                else:
                    lb1, ub1 = None, None

                if constraint_name in _constraints2:
                    c2 = _constraints2[constraint_name]
                    # Handle different constraint formats
                    if isinstance(c2, dict):
                        lb2, ub2 = c2.get("LB"), c2.get("UB")
                    elif isinstance(c2, list | tuple) and len(c2) >= 2:
                        lb2, ub2 = c2[0], c2[1]
                    else:
                        lb2, ub2 = None, None
                else:
                    lb2, ub2 = None, None

                if constraint_name not in _constraints1:
                    status = f"Only in {pb2_name}"
                elif constraint_name not in _constraints2:
                    status = f"Only in {pb1_name}"
                elif (abs(lb1 - lb2) > tolerance if lb1 is not None and lb2 is not None else lb1 != lb2) or (
                    abs(ub1 - ub2) > tolerance if ub1 is not None and ub2 is not None else ub1 != ub2
                ):
                    status = "Modified"
                else:
                    # Check if coefficients are different
                    coeff_different = False
                    if constraint_name in _constraints1 and constraint_name in _constraints2:
                        c1 = _constraints1[constraint_name]
                        c2 = _constraints2[constraint_name]

                        # Get variable coefficients based on format
                        vars1 = {}
                        vars2 = {}

                        if isinstance(c1, dict):
                            vars1 = {k: v for k, v in c1.items() if k not in ["LB", "UB"]}
                        elif isinstance(c1, list | tuple) and len(c1) > 2:
                            vars1 = {var: coeff for var, coeff in c1[2:] if isinstance(var, str)}

                        if isinstance(c2, dict):
                            vars2 = {k: v for k, v in c2.items() if k not in ["LB", "UB"]}
                        elif isinstance(c2, list | tuple) and len(c2) > 2:
                            vars2 = {var: coeff for var, coeff in c2[2:] if isinstance(var, str)}

                        all_vars = set(vars1.keys()) | set(vars2.keys())
                        for var in all_vars:
                            coeff1 = vars1.get(var, 0.0)
                            coeff2 = vars2.get(var, 0.0)
                            if abs(coeff1 - coeff2) > tolerance:
                                coeff_different = True
                                break

                    status = "Modified" if coeff_different else "Identical"

                # Skip identical rows if keep_identical is False
                if not keep_identical and status == "Identical":
                    continue

                f.write(f"{constraint_name},{lb1},{ub1},{lb2},{ub2},{status}\n")

    @staticmethod
    def export_constraint_details_csv(
        pb1,
        pb2,
        filename,
        pb1_name="Before",
        pb2_name="After",
        tolerance=1e-5,
        normalize_names=True,
        keep_identical=True,
    ):
        """
        Export detailed constraint coefficient differences to CSV for better debugging

        :param pb1: dict. First LP problem (from read_lp_* methods)
        :param pb2: dict. Second LP problem (from read_lp_* methods)
        :param filename: str or Path. CSV file to save
        :param pb1_name: str. Name for first problem column
        :param pb2_name: str. Name for second problem column
        :param tolerance: float. Tolerance for numerical comparisons
        :param normalize_names: bool. Whether to normalize constraint/variable names
        :param keep_identical: bool. Whether to keep rows with "Identical" status in the output
        """
        constraints1 = pb1["constraints"]
        constraints2 = pb2["constraints"]

        # Normalize constraint names if requested
        if normalize_names:
            constraints1_normalized = {}
            constraints2_normalized = {}

            for constraint_name, constraint_data in constraints1.items():
                normalized_name = SolverHelper.normalize_variable_name(constraint_name)
                if normalized_name in constraints1_normalized:
                    print(f"Warning: Duplicate normalized constraint name '{normalized_name}' from '{constraint_name}'")
                constraints1_normalized[normalized_name] = constraint_data

            for constraint_name, constraint_data in constraints2.items():
                normalized_name = SolverHelper.normalize_variable_name(constraint_name)
                if normalized_name in constraints2_normalized:
                    print(f"Warning: Duplicate normalized constraint name '{normalized_name}' from '{constraint_name}'")
                constraints2_normalized[normalized_name] = constraint_data

            constraints1 = constraints1_normalized
            constraints2 = constraints2_normalized

        # Filter constraints (keep only those with variables)
        _constraints1 = {}
        _constraints2 = {}

        for k, v in constraints1.items():
            if isinstance(v, dict):
                if len(v) > 2 or any(key not in ["LB", "UB"] for key in v.keys()):
                    _constraints1[k] = v
            elif isinstance(v, list | tuple):
                if len(v) > 2:
                    _constraints1[k] = v

        for k, v in constraints2.items():
            if isinstance(v, dict):
                if len(v) > 2 or any(key not in ["LB", "UB"] for key in v.keys()):
                    _constraints2[k] = v
            elif isinstance(v, list | tuple):
                if len(v) > 2:
                    _constraints2[k] = v

        all_constraints = set(_constraints1.keys()) | set(_constraints2.keys())

        with open(filename, "w") as f:
            f.write(
                f"Constraint,Variable,{pb1_name}_Coefficient,{pb2_name}_Coefficient,Difference,{pb1_name}_LB,{pb1_name}_UB,{pb2_name}_LB,{pb2_name}_UB,Status,Detail\n"
            )

            for constraint_name in sorted(all_constraints):
                # Get bounds
                if constraint_name in _constraints1:
                    c1 = _constraints1[constraint_name]
                    if isinstance(c1, dict):
                        lb1, ub1 = c1.get("LB"), c1.get("UB")
                        vars1 = {k: v for k, v in c1.items() if k not in ["LB", "UB"]}
                    elif isinstance(c1, list | tuple) and len(c1) >= 2:
                        lb1, ub1 = c1[0], c1[1]
                        vars1 = {var: coeff for var, coeff in c1[2:] if isinstance(var, str)}
                    else:
                        lb1, ub1 = None, None
                        vars1 = {}
                else:
                    lb1, ub1 = None, None
                    vars1 = {}

                if constraint_name in _constraints2:
                    c2 = _constraints2[constraint_name]
                    if isinstance(c2, dict):
                        lb2, ub2 = c2.get("LB"), c2.get("UB")
                        vars2 = {k: v for k, v in c2.items() if k not in ["LB", "UB"]}
                    elif isinstance(c2, list | tuple) and len(c2) >= 2:
                        lb2, ub2 = c2[0], c2[1]
                        vars2 = {var: coeff for var, coeff in c2[2:] if isinstance(var, str)}
                    else:
                        lb2, ub2 = None, None
                        vars2 = {}
                else:
                    lb2, ub2 = None, None
                    vars2 = {}

                # Determine overall constraint status
                if constraint_name not in _constraints1:
                    constraint_status = f"Only in {pb2_name}"
                elif constraint_name not in _constraints2:
                    constraint_status = f"Only in {pb1_name}"
                else:
                    # Check bounds difference
                    bounds_different = False
                    if (abs(lb1 - lb2) > tolerance if lb1 is not None and lb2 is not None else lb1 != lb2) or (
                        abs(ub1 - ub2) > tolerance if ub1 is not None and ub2 is not None else ub1 != ub2
                    ):
                        bounds_different = True

                    # Check coefficients difference
                    coeff_different = False
                    all_vars = set(vars1.keys()) | set(vars2.keys())
                    for var in all_vars:
                        coeff1 = vars1.get(var, 0.0)
                        coeff2 = vars2.get(var, 0.0)
                        if abs(coeff1 - coeff2) > tolerance:
                            coeff_different = True
                            break

                    if bounds_different or coeff_different:
                        constraint_status = "Modified"
                    else:
                        constraint_status = "Identical"

                # Skip if identical and keep_identical is False
                if not keep_identical and constraint_status == "Identical":
                    continue

                # Get all variables involved in this constraint
                all_vars_in_constraint = set(vars1.keys()) | set(vars2.keys())

                if len(all_vars_in_constraint) == 0:
                    # Constraint has no variables, just write one row
                    f.write(f"{constraint_name},,,,{lb1},{ub1},{lb2},{ub2},{constraint_status},No variables\n")
                else:
                    # Write a row for each variable in the constraint
                    for idx, var_name in enumerate(sorted(all_vars_in_constraint)):
                        coeff1 = vars1.get(var_name, 0.0)
                        coeff2 = vars2.get(var_name, 0.0)
                        diff = coeff2 - coeff1

                        # Determine variable-level detail
                        if var_name not in vars1:
                            detail = f"Variable only in {pb2_name}"
                        elif var_name not in vars2:
                            detail = f"Variable only in {pb1_name}"
                        elif abs(diff) > tolerance:
                            detail = "Coefficient modified"
                        else:
                            detail = "Coefficient identical"

                        # Only show constraint name and bounds in the first row for this constraint
                        # Subsequent rows for the same constraint will have empty constraint/bounds columns for readability
                        if idx == 0:
                            f.write(
                                f"{constraint_name},{var_name},{coeff1},{coeff2},{diff},{lb1},{ub1},{lb2},{ub2},{constraint_status},{detail}\n"
                            )
                        else:
                            f.write(f",{var_name},{coeff1},{coeff2},{diff},,,,,,{detail}\n")

    @staticmethod
    def compare_lp_problems(
        pb1,
        pb2,
        output_dir=".",
        pb1_name="Legacy",
        pb2_name="Atlas",
        tolerance=1e-5,
        normalize_names=True,
        keep_identical=True,
    ):
        """
        Compare two LP problems, export differences to CSV files, and generate an overall summary report

        Generates the following output files:
        - objective_differences.csv: Comparison of objective function coefficients
        - variable_differences.csv: Comparison of variable bounds
        - constraint_differences.csv: Summary of constraint differences (bounds only)
        - constraint_details.csv: Detailed constraint comparison including all variable coefficients
        - overall_summary_report.txt: Statistical summary of all differences

        :param pb1: dict. First LP problem (from read_lp_* methods)
        :param pb2: dict. Second LP problem (from read_lp_* methods)
        :param output_dir: str or Path. Directory to save CSV files and report
        :param pb1_name: str. Name for first problem (reference for percentages)
        :param pb2_name: str. Name for second problem
        :param tolerance: float. Tolerance for numerical comparisons
        :param normalize_names: bool. Whether to normalize variable/constraint names (remove trailing colons, etc.)
        :param keep_identical: bool. Whether to keep rows with "Identical" status in the CSV output files
        :return: dict with detailed statistics
        """
        from pathlib import Path

        output_dir = Path(output_dir)

        # Export differences to CSV files
        SolverHelper.export_objective_differences_csv(
            pb1,
            pb2,
            output_dir / "objective_differences.csv",
            pb1_name,
            pb2_name,
            tolerance,
            normalize_names,
            keep_identical,
        )
        SolverHelper.export_variable_differences_csv(
            pb1,
            pb2,
            output_dir / "variable_differences.csv",
            pb1_name,
            pb2_name,
            tolerance,
            normalize_names,
            keep_identical,
        )
        SolverHelper.export_constraint_differences_csv(
            pb1,
            pb2,
            output_dir / "constraint_differences.csv",
            pb1_name,
            pb2_name,
            tolerance,
            normalize_names,
            keep_identical,
        )
        # Export detailed constraint coefficient information
        SolverHelper.export_constraint_details_csv(
            pb1,
            pb2,
            output_dir / "constraint_details.csv",
            pb1_name,
            pb2_name,
            tolerance,
            normalize_names,
            keep_identical,
        )

        # Normalize names for analysis
        if normalize_names:
            obj1 = {SolverHelper.normalize_variable_name(k): v for k, v in pb1["objectives"].items()}
            obj2 = {SolverHelper.normalize_variable_name(k): v for k, v in pb2["objectives"].items()}

            vars1 = {SolverHelper.normalize_variable_name(k): v for k, v in pb1["variables"].items()}
            vars2 = {SolverHelper.normalize_variable_name(k): v for k, v in pb2["variables"].items()}

            # Filter constraints with variables
            constraints1 = {}
            constraints2 = {}
            for k, v in pb1["constraints"].items():
                if isinstance(v, dict) and (len(v) > 2 or any(key not in ["LB", "UB"] for key in v.keys())):
                    constraints1[SolverHelper.normalize_variable_name(k)] = v
                elif isinstance(v, list | tuple) and len(v) > 2:
                    constraints1[SolverHelper.normalize_variable_name(k)] = v

            for k, v in pb2["constraints"].items():
                if isinstance(v, dict) and (len(v) > 2 or any(key not in ["LB", "UB"] for key in v.keys())):
                    constraints2[SolverHelper.normalize_variable_name(k)] = v
                elif isinstance(v, list | tuple) and len(v) > 2:
                    constraints2[SolverHelper.normalize_variable_name(k)] = v
        else:
            obj1, obj2 = pb1["objectives"], pb2["objectives"]
            vars1, vars2 = pb1["variables"], pb2["variables"]
            constraints1 = {k: v for k, v in pb1["constraints"].items() if len(v) > 2}
            constraints2 = {k: v for k, v in pb2["constraints"].items() if len(v) > 2}

        # Calculate direct statistics
        def calculate_direct_stats(dict1, dict2, item_type):
            all_items = set(dict1.keys()) | set(dict2.keys())
            identical = 0
            modified = 0
            only_legacy = 0
            only_atlas = 0

            for item in all_items:
                if item not in dict1:
                    only_atlas += 1
                elif item not in dict2:
                    only_legacy += 1
                elif item_type == "objectives":
                    if abs(dict1[item] - dict2[item]) <= tolerance:
                        identical += 1
                    else:
                        modified += 1
                elif item_type == "variables":
                    lb1, ub1 = dict1[item]
                    lb2, ub2 = dict2[item]
                    if abs(lb1 - lb2) <= tolerance and abs(ub1 - ub2) <= tolerance:
                        identical += 1
                    else:
                        modified += 1
                else:  # constraints
                    # Simplified constraint comparison - in practice you'd want more detailed logic
                    identical += 1  # This would need proper implementation

            total_legacy = len(dict1)
            return {
                "identical": identical,
                "modified": modified,
                "only_legacy": only_legacy,
                "only_atlas": only_atlas,
                "total_legacy": total_legacy,
                "total_atlas": len(dict2),
            }

        # Get statistics
        obj_stats = calculate_direct_stats(obj1, obj2, "objectives")
        var_stats = calculate_direct_stats(vars1, vars2, "variables")
        const_stats = calculate_direct_stats(constraints1, constraints2, "constraints")

        # Calculate percentages based on legacy (pb1) as reference
        def calc_percentages(stats):
            total_legacy = stats["total_legacy"]
            if total_legacy == 0:
                return {"identical_pct": 0.0, "modified_pct": 0.0, "only_legacy_pct": 0.0, "extra_atlas_pct": 0.0}

            return {
                "identical_pct": round(stats["identical"] / total_legacy * 100, 2),
                "modified_pct": round(stats["modified"] / total_legacy * 100, 2),
                "only_legacy_pct": round(stats["only_legacy"] / total_legacy * 100, 2),
                "extra_atlas_pct": round(stats["only_atlas"] / total_legacy * 100, 2),
            }

        obj_pct = calc_percentages(obj_stats)
        var_pct = calc_percentages(var_stats)
        const_pct = calc_percentages(const_stats)

        # Create summary report
        summary = {
            "objectives": {
                "total_legacy": obj_stats["total_legacy"],
                "total_atlas": obj_stats["total_atlas"],
                "identical": obj_stats["identical"],
                "modified": obj_stats["modified"],
                "only_legacy": obj_stats["only_legacy"],
                "only_atlas": obj_stats["only_atlas"],
                **obj_pct,
            },
            "variables": {
                "total_legacy": var_stats["total_legacy"],
                "total_atlas": var_stats["total_atlas"],
                "identical": var_stats["identical"],
                "modified": var_stats["modified"],
                "only_legacy": var_stats["only_legacy"],
                "only_atlas": var_stats["only_atlas"],
                **var_pct,
            },
            "constraints": {
                "total_legacy": const_stats["total_legacy"],
                "total_atlas": const_stats["total_atlas"],
                "identical": const_stats["identical"],
                "modified": const_stats["modified"],
                "only_legacy": const_stats["only_legacy"],
                "only_atlas": const_stats["only_atlas"],
                **const_pct,
            },
        }

        # Write summary report to file
        report_file = output_dir / "overall_summary_report.txt"
        with open(report_file, "w") as f:
            f.write("=" * 60 + "\n")
            f.write("LP COMPARISON OVERALL SUMMARY REPORT\n")
            f.write("=" * 60 + "\n\n")

            for category in ["objectives", "variables", "constraints"]:
                stats = summary[category]
                f.write(f"{category.upper()}:\n")
                f.write("-" * 30 + "\n")
                f.write(f"Total in {pb1_name}: {stats['total_legacy']}\n")
                f.write(f"Total in {pb2_name}: {stats['total_atlas']}\n")
                f.write(f"Identical: {stats['identical']} ({stats['identical_pct']}%)\n")
                f.write(f"Modified: {stats['modified']} ({stats['modified_pct']}%)\n")
                f.write(f"Only in {pb1_name}: {stats['only_legacy']} ({stats['only_legacy_pct']}%)\n")
                f.write(
                    f"Extra in {pb2_name}: {stats['only_atlas']} ({stats['extra_atlas_pct']}% of {pb1_name} total)\n"
                )
                f.write("\n")

        return summary

    @staticmethod
    def isfloat(num):
        """
        Test if the given number is a float

        :param num: int or float. Number to test
        :return: True if the number is a float, False else
        """
        try:
            float(num)
            return True
        except ValueError:
            return False

    @staticmethod
    def export_lp_problem(solver, output_path, lp_name, custom_lp_name, print_lp, custom_lp):
        """
        Export a lp problem

        :param solver: ortools.linear_solver.pywraplp.Solver
        :param output_path: str or Path like. Path where to export the problem
        :param lp_name: str. Name of the file where the problem is exported
        :param custom_lp_name: str. Name of the file where the problem with custom export is exported
        :param print_lp: bool. True if the problem must be export else otherwise
        :param custom_lp: bool. True if the problem must be export with custom export otherwise False
        """
        # Save the problem itself for debug:
        if print_lp:
            filename = Path(output_path) / lp_name
            SolverHelper.export_problem_as_lp(solver, filename)
            if custom_lp:
                SolverHelper.custom_export_problem_as_lp(solver, Path(output_path) / custom_lp_name)

    @staticmethod
    def export_lp_solution(solver, status, output_path, lp_solution_name, print_lp):
        """
        Export the lp solution

        :param solver: ortools.linear_solver.pywraplp.Solver
        :param status: ortools.linear_solver.pywraplp.Solver.Status. Status of the solution
        :param output_path: str or Path like. Path where to export the solution
        :param lp_solution_name: str. Name of the file where the solution is exported
        :param print_lp: bool. True if the solution must be export otherwise False
        """
        # Export the solution in a file for debug:
        if print_lp and status in SolverHelper.SOLVED_STATUS:
            filename = Path(output_path) / lp_solution_name
            SolverHelper.export_solution_as_lp(solver, status, filename)

    @staticmethod
    def rebuild_lp_with_real_names(lp_file: str, csv_file: str, new_lp_file: str):
        """
        Rebuild the lp file with the original variables/constraints names.
        :param lp_file: lp file written with shortened names
        :param csv_file: csv file matching the shortened names with the original ones
        :param new_lp_file: lp file with the original variables/constraints names to be written
        """
        names: dict[str, str] = {}
        new_lines = []
        with open(csv_file) as csv:
            csv_lines = csv.readlines()
            csv_lines = SolverHelper.adapt_date_format(csv_lines)
            for id_line, line in enumerate(csv_lines):
                line = line.strip()
                if id_line > 0 and len(line) > 0:  # skip first line and empty line
                    type, short_name, long_name = line.split(";")
                    names[short_name] = long_name
        with open(lp_file) as lp:
            lp_lines = lp.readlines()
            is_binaries = False
            for line in lp_lines:
                if line.startswith("OBJ:"):
                    words = line.strip("\n").split(" ")
                    words.append("\n")
                else:
                    words = line.split(" ")
                new_words = []
                first = True
                if len(words) == 1 and words[0].strip() == "Binaries":
                    is_binaries = True
                    new_lines.append(words[0])
                else:
                    for word in words:
                        if first:
                            # Check if word ends with ":" and remove it for lookup
                            lookup_word = word[:-1] if word.endswith(":") else word
                            if word != "OBJ:" and lookup_word in names.keys():
                                suffix = "" if is_binaries else ":"
                                word = names[lookup_word].replace(" ", "_") + suffix
                            # Special handling for binaries section - variables don't have colons
                            elif is_binaries and word.strip() in names.keys():
                                word = names[word.strip()].replace(" ", "_")
                        else:
                            # For binaries section, also check and replace variable names
                            if is_binaries and word.strip() in names.keys():
                                word = names[word.strip()].replace(" ", "_")
                            elif word in names.keys():
                                word = names[word].replace(" ", "_")
                        new_words.append(word)
                        first = False
                    if is_binaries:
                        new_line = " ".join(new_words) + "\n"
                    else:
                        new_line = " ".join(new_words)
                        new_line = new_line.lstrip()
                    new_lines.append(new_line)
        with open(new_lp_file, "w") as new_lp:
            new_lp.writelines(new_lines)

    @staticmethod
    def adapt_date_format(csv_lines: list[str]) -> list[str]:
        """
        change date format in the given line. Used to ease the comparison between given lp files and lp files exported via OrTools
        :param csv_lines: lines
        :return: lines with the date format changed to yyyy_MM_dd_HH_mm_ss_SS_SS
        """
        lines = []
        # Format 1 : JJ/MM/AAAA HH:MM:SS
        pattern_slash = re.compile(r"(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2}):(\d{2})$")
        # Format 2 : JJ_MM_AAAA_HH:MM:SS
        pattern_underscore = re.compile(r"(\d{2})_(\d{2})_(\d{4})_(\d{2}):(\d{2}):(\d{2})$")
        for line in csv_lines:
            new_line = line.rstrip("\n")
            new_line = pattern_slash.sub(r"\3_\2_\1_\4_\5_\6_00_00", new_line)
            new_line = pattern_underscore.sub(r"\3_\2_\1_\4_\5_\6_00_00", new_line)
            lines.append(new_line + "\n")
        return lines
