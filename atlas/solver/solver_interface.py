"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements OR-Tools optimisation interface.
"""

from typing import Any, Literal

from ortools.linear_solver import pywraplp
from pydantic import BaseModel

from atlas.config import logger
from atlas.enum import SolverStatus
from atlas.timing import timer


class SolutionInfo(BaseModel):
    """Container for optimization solution information.

    :param status: The solver status
    :type status: SolverStatus
    :param objective_value: The optimal objective value if found
    :type objective_value: Optional[float]
    :param solve_time: Time taken to solve in seconds
    :type solve_time: float
    :param num_iterations: Number of iterations performed
    :type num_iterations: Optional[int]
    """

    status: SolverStatus
    objective_value: float | None = None
    solve_time: str | None = None
    num_iterations: int | None = None


class OptimisationModel:
    """
    Unified interface for OR-Tools optimization problems.

    This class provides a consistent API for different types of optimization
    problems including linear programming, mixed-integer programming, and
    constraint programming.
    """

    def __init__(
            self,
            solver_name: str,
            name: str | None = None,
    ):
        """
        Initialize the optimization model.

        :param solver_name: Specific solver name (e.g., 'GLOP', 'SCIP', 'GUROBI')
        :type solver_name: Optional[str]
        """
        self.name = name
        self.solver_name = solver_name
        self._solver = None
        self._variables_name: set[str] = set()
        self._constraints_name: set[str] = set()
        self._objective_dict: dict[str, float] | None = None
        self._objective: Any | None = None
        self._solution_info: SolutionInfo | None = None

        self._initialize_solver()

    def _initialize_solver(self) -> None:
        """Initialize the appropriate solver based on solver type."""
        if self.name:
            logger.debug(f"Initializing optimisation model '{self.name}' with solver :'{self.solver_name}'")
        else:
            logger.debug(f"Initializing optimisation model with solver :'{self.solver_name}'")
        self._solver = pywraplp.Solver.CreateSolver(self.solver_name)

        if self._solver is None:
            raise RuntimeError("Failed to create solver. Check if the solver is available.")

    @property
    def solver(self) -> pywraplp.Solver:
        """Return the underlying OR-Tools solver instance."""
        return self._solver

    @property
    def variables_name(self) -> set[str]:
        """Return the set of decision variables."""
        return self._variables_name

    @property
    def constraints_name(self) -> set[str]:
        """Return the set of constraints."""
        return self._constraints_name

    @property
    def objective(self) -> dict[str, float] | None:
        """Return the current objective coefficients."""
        return self._objective_dict

    @property
    def solution_info(self) -> SolutionInfo | None:
        """Return the last computed solution info."""
        return self._solution_info

    def add_continuous_variable(
            self,
            name: str,
            lower_bound: float = 0.0,
            upper_bound: float = float("inf"),
    ) -> None:
        """
        Add a continuous variable to the model.

        :param name: Variable name
        :type name: str
        :param lower_bound: Lower bound for the variable
        :type lower_bound: float
        :param upper_bound: Upper bound for the variable
        :type upper_bound: float
        """
        logger.debug(f"Adding continuous variable '{name}' with bounds [{lower_bound}, {upper_bound}]")
        if name in self._variables_name:
            raise ValueError(f"Variable '{name}' already exists")
        self._solver.NumVar(lower_bound, upper_bound, name)
        self._variables_name.add(name)

    def add_integer_variable(
            self,
            name: str,
            lower_bound: float = 0.0,
            upper_bound: float = float("inf"),
    ) -> None:
        """
        Add a integer variable to the model.

        :param name: Variable name
        :type name: str
        :param lower_bound: Lower bound for the variable
        :type lower_bound: float
        :param upper_bound: Upper bound for the variable
        :type upper_bound: float
        """
        logger.debug(f"Adding integer variable '{name}' with bounds [{lower_bound}, {upper_bound}]")
        if name in self._variables_name:
            raise ValueError(f"Variable '{name}' already exists")
        self._solver.IntVar(lower_bound, upper_bound, name)
        self._variables_name.add(name)

    def add_boolean_variable(
            self,
            name: str
    ) -> None:
        """
        Add a boolean variable to the model.

        :param name: Variable name
        :type name: str
        :param lower_bound: Lower bound for the variable
        :type lower_bound: float
        :param upper_bound: Upper bound for the variable
        :type upper_bound: float
        """
        logger.debug(f"Adding boolean variable '{name}'")
        if name in self._variables_name:
            raise ValueError(f"Variable '{name}' already exists")
        self._solver.BoolVar(name)
        self._variables_name.add(name)

    def add_continuous_variables(
            self,
            names: list[str],
            lower_bound: float = 0.0,
            upper_bound: float = float("inf"),
    ) -> None:
        """
        Add multiple continuous variables to the model with the same bounds.

        :param name: List of variable names
        :type name: List[str]
        :param lower_bound: Lower bound for the variable
        :type lower_bound: float
        :param upper_bound: Upper bound for the variable
        :type upper_bound: float
        """
        for name in names:
            self.add_continuous_variable(name, lower_bound, upper_bound)

    def add_linear_constraint(
            self,
            coefficients: dict[str, float],
            operator: str,
            rhs: float,
            name: str
    ) -> None:
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
        """
        logger.debug(f"Adding constraint: {coefficients} {operator} {rhs} (name={name})")

        if name in self._constraints_name:
            raise ValueError(f"Constraint '{name}' already exists")

        expr = self._solver.Constraint(-self._solver.infinity(), self._solver.infinity(), name)
        self._constraints_name.add(name)

        for var_name, coeff in coefficients.items():
            if var_name not in self._variables_name:
                raise KeyError(f"Variable '{var_name}' not found")
            variable = self._solver.LookupVariable(var_name)
            expr.SetCoefficient(variable, coeff)

        if operator == "<=":
            expr.SetUb(rhs)
        elif operator == ">=":
            expr.SetLb(rhs)
        elif operator == "==":
            expr.SetBounds(rhs, rhs)
        else:
            raise ValueError(f"Unknown operator: {operator}")

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
        logger.debug(f"Setting objective with direction '{direction}' and coefficients: {coefficients}")

        self._objective = self._solver.Objective()
        self._objective.Clear()

        for var_name, coeff in coefficients.items():
            if var_name not in self._variables_name:
                raise KeyError(f"Variable '{var_name}' not found")
            variable = self._solver.LookupVariable(var_name)
            self._objective.SetCoefficient(variable, coeff)

        if direction == "minimize":
            self._objective.SetMinimization()
        elif direction == "maximize":
            self._objective.SetMaximization()
        else:
            raise ValueError("Optimisation direction not supported.")

        self._objective_dict = coefficients

    def add_objective(self, new_coefficients: dict[str, float]) -> None:
        """
        Add new variables to the existing objective function.

        :param new_coefficients: dictionary mapping variable names to new coefficients
        :type new_coefficients: dict[str, float]
        :raises RuntimeError: If objective was not previously set
        """
        logger.debug(f"Adding to objective: {new_coefficients}")

        if self._objective_dict is None:
            raise RuntimeError("Objective function must be set before it can be modified.")

        for var_name, coeff in new_coefficients.items():
            if var_name not in self._variables_name:
                raise KeyError(f"Variable '{var_name}' not found")

            variable = self._solver.LookupVariable(var_name)
            self._objective.SetCoefficient(variable, coeff)

        self._objective_dict.update(new_coefficients)

    def solve(self, time_limit: float | None = None) -> SolutionInfo:
        """
        Solve the optimization problem.

        :param time_limit: Maximum solving time in seconds
        :type time_limit: Optional[float]
        :return: Solution information
        :rtype: SolutionInfo
        """
        if time_limit:
            logger.debug(f"Setting solver time limit to {time_limit} seconds")
            self._solver.SetTimeLimit(int(time_limit * 1000))

        with timer() as t:
            logger.info(f"Solving the optimisation model {self.name}...")
            status = self._solver.Solve()
        solve_time = t()

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
        logger.info(f"Solve finished in {solve_time} with status: {mapped_status.name}")

        objective_value = None

        if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
            objective_value = self._solver.Objective().Value()

            if objective_value is not None:
                logger.debug(f"Objective value: {objective_value}")

        self._solution_info = SolutionInfo(
            status=mapped_status,
            objective_value=objective_value,
            solve_time=solve_time,
            num_iterations=self._solver.iterations(),
        )

        return self._solution_info

    def get_variable_value(self, name: str) -> float:
        """
        Get the optimal value of a variable.

        :param name: Variable name
        :type name: str
        :return: Variable value
        :rtype: float
        :raises RuntimeError: If model hasn't been solved
        :raises ValueError: If variable hasn't been added
        """
        if not self._solution_info:
            raise RuntimeError("Optimisation model has not been solved yet")

        if name not in self._variables_name:
            raise ValueError(f"Variable '{name}' not found in solution")

        return self._solver.LookupVariable(name).solution_value()

    def export_model(self, filename: str, format_type: Literal["lp", "mps"] = "lp") -> None:
        """
        Export the model to a file.

        :param filename: Output filename
        :type filename: str
        :param format_type: Export format ('lp', 'mps')
        :type format_type: str
        """
        logger.debug(f"Exporting model to '{filename}' with format '{format_type}'")

        if format_type.lower() == "lp":
            lp = self._solver.ExportModelAsLpFormat(False)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
        with open(filename, "w") as f:
            f.write(lp)

    def clear(self) -> None:
        """Clear the model and reset all variables and constraints."""
        self._variables_name.clear()
        self._constraints_name.clear()
        self._objective_dict = None
        self._solution_info = None
        self._objective = None
        self._initialize_solver()

    def __repr__(self) -> str:
        """String representation of the model."""
        stats = self.get_model_stats()
        return (
            f"OptimisationModel(name={self.name},"
            f"solver={self.solver_name},"
            f"variables={stats['num_variables']},"
            f"constraints={stats['num_constraints']})"
        )
