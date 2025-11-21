from pydantic import BaseModel, Field

from atlas.enum import SolverStatus


class SolverOptions(BaseModel):
    """Container for solver options.

    :param presolve: Enable/disable presolve
    :type presolve: bool
    :param duality_gap: Relative MIP gap tolerance (e.g., 0.01 for 1%)
    :type duality_gap: float | None
    """

    presolve: bool = Field(default=True, description="Enable/disable presolve")
    duality_gap: float | None = Field(default=None, description="Relative MIP gap tolerance (e.g., 0.01 for 1%)")
    time_limit: float | None = Field(default=None, description="Time limit in seconds for the solver")


class ConstraintBounds(BaseModel):
    """Container for constraint bounds.

    :param lower_bound: The lower bound of the constraint
    :type lower_bound: float
    :param upper_bound: The upper bound of the constraint
    :type upper_bound: float
    """

    lower_bound: float
    upper_bound: float


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
