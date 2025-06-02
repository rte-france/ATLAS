"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements OR-Tools optimisation interface.
"""

import time
from typing import Any, Literal

from ortools.linear_solver import pywraplp
from pydantic import BaseModel

from atlas.enum import SolverStatus


class SolutionInfo(BaseModel):
    """Container for optimization solution information.

    :param status: The solver status
    :type status: SolverStatus
    :param objective_value: The optimal objective value if found
    :type objective_value: Optional[float]
    :param solve_time: Time taken to solve in seconds
    :type solve_time: float
    :param variables: dictionary of variable names to their optimal values
    :type variables: dict[str, float]
    :param num_iterations: Number of iterations performed
    :type num_iterations: Optional[int]
    """

    status: SolverStatus
    objective_value: float | None = None
    solve_time: float = 0.0
    variables: dict[str, float] = None
    num_iterations: int | None = None

    def __post_init__(self):
        if self.variables is None:
            self.variables = {}


class OptimisationModel:
    """
    Unified interface for OR-Tools optimization problems.

    This class provides a consistent API for different types of optimization
    problems including linear programming, mixed-integer programming, and
    constraint programming.
    """

    def __init__(self, solver_name: str):
        """
        Initialize the optimization model.

        :param solver_name: Specific solver name (e.g., 'GLOP', 'SCIP', 'GUROBI')
        :type solver_name: Optional[str]
        """
        self.solver_name = solver_name
        self._solver = None
        self._variables: dict[str, Any] = {}
        self._constraints: list[Any] = []
        self._objective = None
        self._solution_info: SolutionInfo | None = None

        self._initialize_solver()

    def _initialize_solver(self) -> None:
        """Initialize the appropriate solver based on solver type."""
        self._solver = pywraplp.Solver.CreateSolver(self.solver_name)

        if self._solver is None:
            raise RuntimeError("Failed to create solver. Check if the solver is available.")

    @property
    def solver(self) -> pywraplp.Solver:
        """Return the underlying OR-Tools solver instance."""
        return self._solver

    @property
    def variables(self) -> dict[str, Any]:
        """Return the dictionary of decision variables."""
        return self._variables

    @property
    def constraints(self) -> list[Any]:
        """Return the list of constraints."""
        return self._constraints

    @property
    def objective(self) -> dict[str, float] | None:
        """Return the current objective coefficients."""
        return self._objective

    @property
    def solution_info(self) -> SolutionInfo | None:
        """Return the last computed solution info."""
        return self._solution_info

    def add_variable(
        self,
        name: str,
        lower_bound: float = 0.0,
        upper_bound: float = float("inf"),
        var_type: str = "continuous",
    ) -> Any:
        """
        Add a decision variable to the model.

        :param name: Variable name
        :type name: str
        :param lower_bound: Lower bound for the variable
        :type lower_bound: float
        :param upper_bound: Upper bound for the variable
        :type upper_bound: float
        :param var_type: Variable type ('continuous', 'integer', 'binary')
        :type var_type: str
        :return: The created variable object
        :rtype: Any
        """
        if name in self._variables:
            raise ValueError(f"Variable '{name}' already exists")

        if var_type == "continuous":
            var = self._solver.NumVar(lower_bound, upper_bound, name)
        elif var_type == "integer":
            var = self._solver.IntVar(lower_bound, upper_bound, name)
        elif var_type == "binary":
            var = self._solver.BoolVar(name)
        else:
            raise ValueError(f"Unknown variable type: {var_type}")

        self._variables[name] = var
        return var

    def add_variables(
        self,
        names: list[str],
        lower_bound: float = 0.0,
        upper_bound: float = float("inf"),
        var_type: str = "continuous",
    ) -> dict[str, Any]:
        """
        Add multiple decision variables to the model.

        :param names: List of variable names
        :type names: List[str]
        :param lower_bound: Lower bound for all variables
        :type lower_bound: float
        :param upper_bound: Upper bound for all variables
        :type upper_bound: float
        :param var_type: Variable type for all variables
        :type var_type: str
        :return: dictionary mapping variable names to variable objects
        :rtype: dict[str, Any]
        """
        variables = {}
        for name in names:
            variables[name] = self.add_variable(name, lower_bound, upper_bound, var_type)
        return variables

    def get_variable(self, name: str) -> Any:
        """
        Get a variable by name.

        :param name: Variable name
        :type name: str
        :return: Variable object
        :rtype: Any
        :raises KeyError: If variable doesn't exist
        """
        if name not in self._variables:
            raise KeyError(f"Variable '{name}' not found")
        return self._variables[name]

    def add_linear_constraint(
        self, coefficients: dict[str, float], operator: str, rhs: float, name: str | None = None
    ) -> Any:
        """
        Add a linear constraint of the form: sum(coeff * var) operator rhs.

        :param coefficients: dictionary mapping variable names to coefficients
        :type coefficients: dict[str, float]
        :param operator: Constraint operator ('<=', '>=', '==')
        :type operator: str
        :param rhs: Right-hand side value
        :type rhs: float
        :param name: Optional constraint name
        :type name: Optional[str]
        :return: Constraint object
        :rtype: Any
        """
        # Create linear expression
        expr = self._solver.Constraint(-self._solver.infinity(), self._solver.infinity())

        for var_name, coeff in coefficients.items():
            if var_name not in self._variables:
                raise KeyError(f"Variable '{var_name}' not found")
            expr.SetCoefficient(self._variables[var_name], coeff)

        # Set bounds based on operator
        if operator == "<=":
            expr.SetUb(rhs)
        elif operator == ">=":
            expr.SetLb(rhs)
        elif operator == "==":
            expr.SetBounds(rhs, rhs)
        else:
            raise ValueError(f"Unknown operator: {operator}")

        self._constraints.append(expr)

    def set_objective(
        self,
        coefficients: dict[str, float],
        direction: Literal["maximize", "minimize"] = "maximize",
    ) -> None:
        """
        Set the objective function.

        :param coefficients: dictionary mapping variable names to objective coefficients
        :type coefficients: dict[str, float]
        :param direction: Optimization direction
        :type direction: OptimizationDirection
        """

        objective = self._solver.Objective()
        objective.Clear()

        for var_name, coeff in coefficients.items():
            if var_name not in self._variables:
                raise KeyError(f"Variable '{var_name}' not found")
            objective.SetCoefficient(self._variables[var_name], coeff)

        if direction == "minimize":
            objective.SetMinimization()
        elif direction == "maximize":
            objective.SetMaximization()
        else:
            raise ValueError("Optimisation direction not supported.")

        self._objective = coefficients

    def solve(self, time_limit: float | None = None) -> SolutionInfo:
        """
        Solve the optimization problem.

        :param time_limit: Maximum solving time in seconds
        :type time_limit: Optional[float]
        :return: Solution information
        :rtype: SolutionInfo
        """
        start_time = time.time()

        if time_limit:
            self._solver.SetTimeLimit(int(time_limit * 1000))  # Convert to milliseconds

        status = self._solver.Solve()
        solve_time = time.time() - start_time

        status_map = {
            pywraplp.Solver.OPTIMAL: SolverStatus.OPTIMAL,
            pywraplp.Solver.FEASIBLE: SolverStatus.FEASIBLE,
            pywraplp.Solver.INFEASIBLE: SolverStatus.INFEASIBLE,
            pywraplp.Solver.UNBOUNDED: SolverStatus.UNBOUNDED,
            pywraplp.Solver.ABNORMAL: SolverStatus.ABNORMAL,
            pywraplp.Solver.NOT_SOLVED: SolverStatus.NOT_SOLVED,
            pywraplp.Solver.MODEL_INVALID: SolverStatus.MODEL_INVALID,
        }

        mapped_status = status_map.get(status, SolverStatus.NOT_SOLVED)

        variables = {}
        objective_value = None

        if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
            objective_value = self._solver.Objective().Value()
            for name, var in self._variables.items():
                variables[name] = var.solution_value()

        self._solution_info = SolutionInfo(
            status=mapped_status,
            objective_value=objective_value,
            solve_time=solve_time,
            variables=variables,
            num_iterations=self._solver.iterations(),
        )

        return self._solution_info

    def get_solution(self) -> SolutionInfo | None:
        """
        Get the last solution information.

        :return: Solution information or None if not solved
        :rtype: Optional[SolutionInfo]
        """
        return self._solution_info

    def get_variable_value(self, name: str) -> float:
        """
        Get the optimal value of a variable.

        :param name: Variable name
        :type name: str
        :return: Variable value
        :rtype: float
        :raises RuntimeError: If model hasn't been solved or variable not found
        """
        if not self._solution_info or not self._solution_info.variables:
            raise RuntimeError("Model has not been solved yet")

        if name not in self._solution_info.variables:
            raise KeyError(f"Variable '{name}' not found in solution")

        return self._solution_info.variables[name]

    def export_model(self, filename: str, format_type: Literal["lp", "mps"] = "lp") -> None:
        """
        Export the model to a file.

        :param filename: Output filename
        :type filename: str
        :param format_type: Export format ('lp', 'mps')
        :type format_type: str
        """
        if format_type.lower() == "lp":
            pywraplp.ExportModelAsLpFormat(filename)
        elif format_type.lower() == "mps":
            self._solver.ExportModelAsMpsFormat(filename)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")

    def clear(self) -> None:
        """Clear the model and reset all variables and constraints."""
        self._variables.clear()
        self._constraints.clear()
        self._objective = None
        self._solution_info = None
        self._initialize_solver()

    def get_model_stats(self) -> dict[str, Any]:
        """
        Get model statistics.

        :return: dictionary containing model statistics
        :rtype: dict[str, Any]
        """
        stats = {
            "num_variables": len(self._variables),
            "num_constraints": len(self._constraints),
            "has_objective": self._objective is not None,
            "num_continuous_variables": self._solver.NumVariables(),
        }

        return stats

    def __repr__(self) -> str:
        """String representation of the model."""
        stats = self.get_model_stats()
        return (
            f"OptimisationModel(solver={self.solver_name},"
            f"variables={stats['num_variables']},"
            f"constraints={stats['num_constraints']})"
        )
