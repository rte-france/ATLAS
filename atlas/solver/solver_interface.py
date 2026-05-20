"""
Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Module that implements OR-Tools optimisation interface.
"""

from pathlib import Path
from typing import Any, Literal

from ortools.linear_solver import pywraplp

from atlas.config import logger
from atlas.enums import SolverEnum, SolverStatus
from atlas.solver.models import ConstraintBounds, SolutionInfo, SolverOptions
from atlas.solver.solver_parameters import (
    GenericParameterBuilder,
    SCIPParameterBuilder,
    SolverParameterBuilder,
    XPRESSParameterBuilder,
)
from atlas.timing import timer


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
        options: SolverOptions | None = None,
    ):
        """
        Initialize the optimization model.

        :param solver_name: Specific solver name (e.g., 'GLOP', 'SCIP', 'GUROBI')
        :type solver_name: Optional[str]
        :param name: Optional name for the model
        :type name: Optional[str]
        :param options: Solver options (presolve, duality_gap, etc.)
        :type options: Optional[SolverOptions]
        """
        self.name = name
        self._solver = None
        self._variables_name: set[str] = set()
        self._constraints_name: set[str] = set()
        self._objective: Any | None = None
        self._objective_direction: Literal["maximize", "minimize"] | None = None
        self._objective_pending: bool = False
        self._solution_info: SolutionInfo | None = None
        self._options: SolverOptions = options if options is not None else SolverOptions()

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

        self._parameter_builder = self._get_parameter_builder()

    def _get_parameter_builder(self) -> SolverParameterBuilder:
        """Get the appropriate parameter builder for the current solver.

        :return: Parameter builder instance for the current solver
        :rtype: SolverParameterBuilder
        """
        if self.solver_name == SolverEnum.XPRESS:
            return XPRESSParameterBuilder(self._solver)
        elif self.solver_name == SolverEnum.SCIP:
            return SCIPParameterBuilder(self._solver)
        else:
            return GenericParameterBuilder(self._solver)

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

    @property
    def options(self) -> SolverOptions:
        """Return the current solver options."""
        return self._options

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

    def get_constraint_bounds(self, name: str) -> ConstraintBounds:
        """
        Get the bounds of a constraint by name.

        :param name: Constraint name
        :type name: str
        :return: Tuple containing (lower_bound, upper_bound)
        :rtype: ConstraintBounds
        :raises ValueError: If constraint doesn't exist
        """
        constraint = self.get_constraint(name)
        return ConstraintBounds(
            lower_bound=constraint.lb(),
            upper_bound=constraint.ub(),
        )

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

    def set_direction(self, direction: Literal["maximize", "minimize"]) -> None:
        """
        Set the optimization direction for the model.

        This method can only be called once. Once set, the direction is immutable
        and cannot be changed. This ensures consistency when building the objective
        function incrementally.

        :param direction: Optimization direction ("maximize" or "minimize")
        :type direction: Literal["maximize", "minimize"]
        :raises ValueError: If direction has already been set
        :raises ValueError: If direction is not "maximize" or "minimize"
        """
        if self._objective_direction is not None:
            raise ValueError(
                f"Optimization direction is already set to '{self._objective_direction}' and cannot be changed. "
                f"Direction must be set only once."
            )

        if direction not in ["maximize", "minimize"]:
            raise ValueError(f"Direction must be 'maximize' or 'minimize', got '{direction}'")

        logger.debug(f"Setting optimization direction to '{direction}'")
        self._objective_direction = direction

    def add_objective(self, objective_expr: Any) -> None:
        """
        Add terms to the objective function.

        This method allows you to incrementally build the objective function by adding
        terms one at a time. The optimization direction must be set using set_direction()
        before calling this method.

        **Example**

            model.set_direction("maximize")
            model.add_objective(x + 2 * y)
            model.add_objective(3 * z)  # Adds to existing objective

        :param objective_expr: OR-Tools expression to add to the objective
        :type objective_expr: Any (OR-Tools expression object)
        :raises ValueError: If direction has not been set via set_direction()
        """
        if self._objective_direction is None:
            raise ValueError(
                "Optimization direction must be set before adding objective terms. "
                "Call set_direction('maximize') or set_direction('minimize') first."
            )

        if self._objective is None:
            self._objective = objective_expr
        else:
            self._objective = self._objective + objective_expr

        self._objective_pending = True

    def set_objective(self, objective_expr: Any) -> None:
        """
        Set the objective function using OR-Tools expression syntax.

        This method replaces any existing objective function. Use add_objective()
        if you want to incrementally build the objective. The optimization direction
        must be set using set_direction() before calling this method.

        This method allows you to set objectives directly like:

        **Example**

            model.set_direction("maximize")
            model.set_objective(x + 2 * y)

        :param objective_expr: OR-Tools expression for the objective
        :type objective_expr: Any (OR-Tools expression object)
        :raises ValueError: If direction has not been set via set_direction()
        """
        if self._objective_direction is None:
            raise ValueError(
                "Optimization direction must be set before setting objective. "
                "Call set_direction('maximize') or set_direction('minimize') first."
            )

        logger.debug("Setting objective expression")
        self._objective = objective_expr
        self._update_solver_objective()
        self._objective_pending = False

    def _update_solver_objective(self) -> None:
        """
        Update the solver's objective function based on the current direction.

        This helper method is called after objective terms are added or set to
        synchronize the internal objective expression with the OR-Tools solver.

        :raises ValueError: If objective direction is not set or is invalid
        """
        if self._objective_direction == "minimize":
            self._solver.Minimize(self._objective)
        elif self._objective_direction == "maximize":
            self._solver.Maximize(self._objective)
        else:
            raise ValueError(f"Invalid optimization direction: {self._objective_direction}")

    def solve(self) -> SolutionInfo:
        """
        Solve the optimization problem.

        :return: Solution information
        :rtype: SolutionInfo
        """
        if self._objective_pending:
            self._update_solver_objective()
            self._objective_pending = False
        self._apply_solver_options()

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
        if not self.name:
            logger.info(f"Optimisation finished in {solve_time} with status: {mapped_status.name}")
        else:
            logger.info(f"{self.name} optimisation finished in {solve_time} with status: {mapped_status.name}")

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

    def export_model(self, filename: str | Path) -> None:
        """
        Export the model to a file.

        :param filename: Output filename
        :type filename: str
        """
        if self._objective_pending:
            self._update_solver_objective()
            self._objective_pending = False
        logger.debug(f"Exporting model to '{filename}'")

        lp = self._solver.ExportModelAsLpFormat(False)

        with open(filename, "w") as f:
            f.write(lp)

    def _apply_solver_options(self) -> None:
        """Apply solver options to the underlying solver using the parameter builder."""
        if self._options is None:
            return

        self._parameter_builder.apply_options(self._options)

    def set_solver_options(self, options: SolverOptions) -> None:
        """
        Update solver options.

        :param options: New solver options
        :type options: SolverOptions
        """
        logger.debug(f"Updating solver options to: {options}")
        self._options = options

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
        self._objective_pending = False
        self._initialize_solver(self.solver_name)

    def deactivate_constraint(self, constraint_name: str) -> None:
        """
        Deactivate a constraint by setting its bounds to (-inf, +inf)

        :param constraint_name: Name of the constraint to deactivate
        :type constraint_name: str
        :raises ValueError: If constraint doesn't exist
        """
        logger.debug(f"Deactivating constraint '{constraint_name}'")
        constraint = self.get_constraint(constraint_name)
        constraint.SetBounds(float("-inf"), float("inf"))

    def __repr__(self) -> str:
        """String representation of the model."""
        return f"OptimisationModel(name={self.name},solver={self.solver_name.value})"
