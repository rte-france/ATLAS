from pydantic import BaseModel, ConfigDict, Field

from atlas.enums import SolverStatus
from atlas.validators import DurationField

SUCCESSFUL_SOLVER_STATUSES = (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
"""Statuses for which the solver actually holds a solution that can be read back."""


class SolverOptions(BaseModel):
    """Container for solver options.

    :param presolve: Enable/disable presolve
    :type presolve: bool
    :param duality_gap: Relative MIP gap tolerance (e.g., 0.01 for 1%)
    :type duality_gap: float | None
    :param time_limit: Time limit in seconds for the solver
    :type time_limit: float | None
    :param num_threads: Number of threads to use for parallel solving
    :type num_threads: int | None
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    presolve: bool = Field(default=True, description="Enable/disable presolve")
    duality_gap: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Relative MIP gap tolerance (e.g., 0.01 for 1%)"
    )
    time_limit: DurationField | None = Field(default=None, description="Time limit in seconds for the solver")


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

    @property
    def is_successful(self) -> bool:
        """Whether the solve produced a usable solution.

        Only ``OPTIMAL`` and ``FEASIBLE`` carry variable values: for every other status the solver
        leaves its variables at their default ``0.0``, which reads like a valid solution but is not.

        :return: True if the solution can be read, False otherwise
        :rtype: bool
        """
        return self.status in SUCCESSFUL_SOLVER_STATUSES
