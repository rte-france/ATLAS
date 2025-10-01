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
from atlas.enum import SolverEnum, SolverStatus
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
        solver_name: SolverEnum | str,
        name: str | None = None,
    ):
        """
        Initialize the optimization model.

        :param solver_name: Specific solver name (e.g., 'GLOP', 'SCIP', 'GUROBI')
        :type solver_name: Optional[str]
        """
        self.name = name
        self._solver = None
        self._variables_name: set[str] = set()
        self._constraints_name: set[str] = set()
        self._objective: Any | None = None
        self._objective_direction: Literal["maximize", "minimize"] | None = None
        self._solution_info: SolutionInfo | None = None

        self._initialize_solver(solver_name)

    def _initialize_solver(self, solver_name: str | SolverEnum) -> None:
        """Initialize the appropriate solver based on solver type."""
        if isinstance(solver_name, str):
            solver_name = solver_name.upper()
        self.solver_name = SolverEnum(solver_name)
        if self.name:
            logger.debug(f"Initializing optimisation model '{self.name}' with solver :'{self.solver_name.value}'")
        else:
            logger.debug(f"Initializing optimisation model with solver :'{self.solver_name.value}'")
        self._solver = pywraplp.Solver.CreateSolver(self.solver_name.value)

        if self._solver is None:
            raise RuntimeError("Failed to create solver. Check if the solver is available.")

    @property
    def solver(self) -> pywraplp.Solver:
        """Return the underlying OR-Tools solver instance."""
        return self._solver

    @property
    def variables(self) -> set[str]:
        """Return the set of decision variables."""
        return self._variables_name

    @property
    def constraints(self) -> set[str]:
        """Return the set of constraints."""
        return self._constraints_name

    @property
    def solution_info(self) -> SolutionInfo | None:
        """Return the last computed solution info."""
        return self._solution_info

    def add_continuous_variable(
        self,
        name: str,
        lower_bound: float = float("-inf"),
        upper_bound: float = float("inf"),
    ) -> Any:
        """
        Add a continuous variable to the model.

        :param name: Variable name
        :type name: str
        :param lower_bound: Lower bound for the variable
        :type lower_bound: float
        :param upper_bound: Upper bound for the variable
        :type upper_bound: float
        :return: OR-Tools variable object that can be used in expressions
        :rtype: pywraplp.Variable
        """
        logger.debug(f"Adding continuous variable '{name}' with bounds [{lower_bound}, {upper_bound}]")
        if name in self._variables_name:
            raise ValueError(f"Variable '{name}' already exists")

        var = self._solver.NumVar(lower_bound, upper_bound, name)
        self._variables_name.add(name)
        return var

    def add_integer_variable(
        self,
        name: str,
        lower_bound: float = 0.0,
        upper_bound: float = float("inf"),
    ) -> Any:
        """
        Add a integer variable to the model.

        :param name: Variable name
        :type name: str
        :param lower_bound: Lower bound for the variable
        :type lower_bound: float
        :param upper_bound: Upper bound for the variable
        :type upper_bound: float
        :return: OR-Tools variable object that can be used in expressions
        :rtype: pywraplp.Variable
        """
        logger.debug(f"Adding integer variable '{name}' with bounds [{lower_bound}, {upper_bound}]")
        if name in self._variables_name:
            raise ValueError(f"Variable '{name}' already exists")

        var = self._solver.IntVar(lower_bound, upper_bound, name)
        self._variables_name.add(name)
        return var

    def add_boolean_variable(self, name: str) -> Any:
        """
        Add a boolean variable to the model.

        :param name: Variable name
        :type name: str
        :return: OR-Tools variable object that can be used in expressions
        :rtype: pywraplp.Variable
        """
        logger.debug(f"Adding boolean variable '{name}'")
        if name in self._variables_name:
            raise ValueError(f"Variable '{name}' already exists")

        var = self._solver.BoolVar(name)
        self._variables_name.add(name)
        return var

    def get_variable(self, name: str) -> Any:
        """
        Get a variable object by name for use in expressions.

        :param name: Variable name
        :type name: str
        :return: OR-Tools variable object
        :rtype: pywraplp.Variable
        :raises ValueError: If variable doesn't exist
        """
        if name not in self._variables_name:
            raise ValueError(f"Variable '{name}' not found")
        return self._solver.LookupVariable(name)

    def add_constraint(self, constraint_expr: Any, name: str | None = None) -> None:
        """
        Add a constraint using OR-Tools expression syntax.

        This method allows you to pass constraints directly like:
        model.add_constraint(x + y <= 10, "sum_constraint")
        model.add_constraint(2 * x + 3 * y >= 5, "min_constraint")
        model.add_constraint(x == y, "equality_constraint")

        :param constraint_expr: OR-Tools constraint expression
        :type constraint_expr: Any (OR-Tools constraint object)
        :param name: Optional constraint name
        :type name: Optional[str]
        """
        if name is None:
            name = f"constraint_{len(self._constraints_name)}"

        if name in self._constraints_name:
            raise ValueError(f"Constraint '{name}' already exists")

        logger.debug(f"Adding constraint: {name}")

        self._solver.Add(constraint_expr, name)
        self._constraints_name.add(name)

    def get_constraint(self, name: str) -> Any:
        """
        Get a constraint object by name for use in expressions.

        :param name: Constraint name
        :type name: str
        :return: OR-Tools constraint object
        :rtype: pywraplp.Constraint
        :raises ValueError: If constraint doesn't exist
        """
        if name not in self._constraints_name:
            raise ValueError(f"Constraint '{name}' not found")
        return self._solver.LookupConstraint(name)

    def add_objective(
        self,
        objective_expr: Any,
        direction: Literal["maximize", "minimize"] = "maximize",
    ) -> None:
        """
        Add terms to the objective function.

        This method allows you to incrementally build the objective function by adding
        terms one at a time. If this is the first call, it sets the optimization direction.
        Subsequent calls must use the same direction.

        Examples:
        model.add_objective(x + 2 * y, "maximize")
        model.add_objective(3 * z, "maximize")  # Adds to existing objective

        :param objective_expr: OR-Tools expression to add to the objective
        :type objective_expr: Any (OR-Tools expression object)
        :param direction: Optimization direction (must be consistent across calls)
        :type direction: Literal["maximize", "minimize"]
        :raises ValueError: If direction differs from previously set direction
        """
        if self._objective is None:
            logger.debug(f"Initializing objective with direction '{direction}'")
            self._objective_direction = direction
            self._objective = objective_expr
        else:
            if self._objective_direction is None:
                self._objective_direction = direction
            elif direction != self._objective_direction:
                raise ValueError(
                    f"Objective direction '{direction}' conflicts with previously set direction "
                    f"'{self._objective_direction}'"
                )
            logger.debug(f"Adding term to existing objective with direction '{direction}'")
            self._objective = self._objective + objective_expr

        if self._objective_direction == "minimize":
            self._solver.Minimize(self._objective)
        elif self._objective_direction == "maximize":
            self._solver.Maximize(self._objective)
        else:
            raise ValueError(f"Unsupported optimization direction: {self._objective_direction}")

    def set_objective(
        self,
        objective_expr: Any,
        direction: Literal["maximize", "minimize"] = "maximize",
    ) -> None:
        """
        Set the objective function using OR-Tools expression syntax.

        This method replaces any existing objective function. Use add_objective()
        if you want to incrementally build the objective.

        This method allows you to set objectives directly like:
        model.set_objective(x + 2 * y, "maximize")
        model.set_objective(3 * x - y + 5, "minimize")

        :param objective_expr: OR-Tools expression for the objective
        :type objective_expr: Any (OR-Tools expression object)
        :param direction: Optimization direction
        :type direction: Literal["maximize", "minimize"]
        """
        logger.debug(f"Setting objective expression with direction '{direction}'")

        self._objective = objective_expr
        self._objective_direction = direction

        if direction == "minimize":
            self._solver.Minimize(objective_expr)
        elif direction == "maximize":
            self._solver.Maximize(objective_expr)
        else:
            raise ValueError("Optimisation direction not supported.")

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

    def get_constraint_slack_value(self, name: str) -> float:
        """
        Get the slack value of a constraint.

        :param name: constraint name
        :type name: str
        :return: Slack value of the constraint
        :rtype: float
        :raises RuntimeError: If model hasn't been solved
        :raises ValueError: If constraint hasn't been added
        """
        if not self._solution_info:
            raise RuntimeError("Optimisation model has not been solved yet")

        if name not in self._constraints_name:
            raise ValueError(f"Constraint '{name}' not found in model")

        constraint = self._solver.LookupConstraint(name)
        sum_coeff = sum([constraint.GetCoefficient(var) * var.solution_value() for var in self._solver.variables()])
        slack_value = constraint.ub() - sum_coeff if constraint.ub() != float("inf") else constraint.lb() - sum_coeff
        return slack_value

    def export_model(self, filename: str) -> None:
        """
        Export the model to a file.

        :param filename: Output filename
        :type filename: str
        :param format_type: Export format ('lp', 'mps')
        :type format_type: str
        """
        logger.debug(f"Exporting model to '{filename}'")

        lp = self._solver.ExportModelAsLpFormat(False)

        with open(filename, "w") as f:
            f.write(lp)

    def set_solver_specific_parameters_as_string(self, params: str) -> bool:
        """
        Pass solver specific parameters in text format.

        :param params: Specific parameters
        :return: Returns true if the operation was successful.
        """
        return self._solver.SetSolverSpecificParametersAsString(params)

    def clear(self) -> None:
        """Clear the model and reset all variables and constraints."""
        self._variables_name.clear()
        self._constraints_name.clear()
        self._solution_info = None
        self._objective = None
        self._objective_direction = None
        self._initialize_solver(self.solver_name)

    def __repr__(self) -> str:
        """String representation of the model."""
        return f"OptimisationModel(name={self.name},solver={self.solver_name.value})"
