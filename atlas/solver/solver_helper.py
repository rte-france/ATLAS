"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import re
from collections import OrderedDict
from pathlib import Path

import dictdiffer
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
        diffs = list(dictdiffer.diff(solution1, solution2, tolerance=tolerance, absolute_tolerance=absolute_tolerance))
        return len(diffs) == 0

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
                    if len(line) == 2:
                        lb, var_name = line
                        ub = "inf"
                    else:
                        lb, var_name, ub = line
                    variables[var_name] = [float(lb), float(ub)]

            elif section == "binary":
                var_name = line
                binaries.append(var_name)

        return objectives, constraints, variables, binaries

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

        return objectives, constraints, variables, binaries

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

        return objectives, constraints, variables, binaries

    @staticmethod
    def compare_lp_problems(pb1, pb2, tolerance=1e-5):
        """
        Test if the given number is a float

        :param pb1: int or float. Number to test
        :param pb2: int or float. Number to test
        :param tolerance: int or float. Number to test
        :return: True if the number is a float, False else
        """
        constraints1 = pb1["constraints"]
        constraints2 = pb2["constraints"]
        _constraints1 = OrderedDict()
        _constraints2 = OrderedDict()

        for key, value in constraints1.items():
            # Don't keep constraints with only LB and UB element
            if len(value) > 2:
                _constraints1[key] = value

        for key, value in constraints2.items():
            if len(value) > 2:
                _constraints2[key] = value
        diff_constraint = list(dictdiffer.diff(_constraints1, _constraints2, tolerance=tolerance))

        diff_variables = list(dictdiffer.diff(pb1["variables"], pb2["variables"], tolerance=tolerance))
        diff_objectives = list(dictdiffer.diff(pb1["objectives"], pb2["objectives"], tolerance=tolerance))

        return diff_constraint, diff_variables, diff_objectives

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
                words = line.split(" ")
                new_words = []
                first = True
                if len(words) == 1 and words[0].strip() == "Binaries":
                    is_binaries = True
                    new_lines.append(words[0])
                else:
                    for word in words:
                        if first:
                            if word != "OBJ:" and word[:-1] in names.keys():
                                suffix = "" if is_binaries else ":"
                                word = names[word[:-1]].replace(" ", "_") + suffix
                        else:
                            if word in names.keys():
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
        lines = []
        # Format 1 : JJ/MM/AAAA HH:MM:SS
        pattern_slash = re.compile(r"(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2}):(\d{2})$")
        # Format 2 : JJ_MM_AAAA_HH:MM:SS
        pattern_underscore = re.compile(r"(\d{2})_(\d{2})_(\d{4})_(\d{2}):(\d{2}):(\d{2})$")
        for line in csv_lines:
            new_line = line.rstrip("\n")
            # Remplace format slash
            new_line = pattern_slash.sub(r"\3_\2_\1_\4_\5_\6_00_00", new_line)
            # Remplace format underscore
            new_line = pattern_underscore.sub(r"\3_\2_\1_\4_\5_\6_00_00", new_line)
            lines.append(new_line + "\n")
        return lines


if __name__ == "__main__":
    # rewrite lp with real variables names
    lp = "D:\\Projets\\ATLAS\\Refonte_DAO_Tests\\es_battery_lp.lp"
    csv_path = "D:\\Projets\\ATLAS\\Refonte_DAO_Tests\\es_battery_lp.lp_correspondance.csv"
    new_lp = "D:\\Projets\\ATLAS\\Refonte_DAO_Tests\\es_battery_lpNEW.lp"
    SolverHelper.rebuild_lp_with_real_names(lp, csv_path, new_lp)

    # Check that both lp are the same
    lp_ATLAS = "D:\\Projets\\ATLAS\\code\\ATLAS\\atlas\\modules\\day_ahead_orders\\storage_es_battery.lp"
    objectives_a, constraints_a, variables_a, binaries_a = SolverHelper.read_lp_ortools(lp_ATLAS)
    objectives_p, constraints_p, variables_p, binaries_p = SolverHelper.read_lp_legacy(new_lp)

    assert len(objectives_a) == len(objectives_p)
    assert len(constraints_a) == len(constraints_p)
    assert len(variables_a) == len(variables_p)
    assert len(binaries_a) == len(binaries_p)
