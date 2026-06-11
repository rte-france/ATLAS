from abc import ABC, abstractmethod

from ortools.linear_solver import pywraplp  # type: ignore  [attr-defined]

from atlas.core.solver.models import SolverOptions


class SolverParameterBuilder(ABC):
    """Abstract base class for solver-specific parameter builders."""

    def __init__(self, solver: pywraplp.Solver):
        """Initialize the parameter builder with a solver instance.

        :param solver: OR-Tools solver instance
        :type solver: pywraplp.Solver
        """
        self.solver = solver

    @abstractmethod
    def apply_options(self, options: SolverOptions) -> None:
        """Apply solver options to the solver instance.

        :param options: Solver options to apply
        :type options: SolverOptions
        """
        pass


class XPRESSParameterBuilder(SolverParameterBuilder):
    """Parameter builder for XPRESS solver."""

    def apply_options(self, options: SolverOptions) -> None:
        """Apply options using XPRESS-specific parameter names.

        XPRESS uses different parameter names:
        - MAXTIME instead of time limit in seconds
        - MIPRELSTOP instead of relative_mip_gap
        - PRESOLVE 0/1 instead of presolve on/off

        :param options: Solver options to apply
        :type options: SolverOptions
        """
        param_parts = []

        if options.time_limit is not None:
            # Convert Duration to milliseconds
            time_limit_ms = int(options.time_limit.total_seconds() * 1000)
            self.solver.SetTimeLimit(time_limit_ms)

        if options.duality_gap is not None:
            param_parts.append(f"MIPRELSTOP {options.duality_gap}")

        if not options.presolve:
            param_parts.append("PRESOLVE 0")
        else:
            param_parts.append("PRESOLVE 1")

        if param_parts:
            param_string = " ".join(param_parts)
            self.solver.SetSolverSpecificParametersAsString(param_string)


class SCIPParameterBuilder(SolverParameterBuilder):
    """Parameter builder for SCIP solver."""

    def apply_options(self, options: SolverOptions) -> None:
        """Apply options using SCIP-specific parameter format.

        SCIP requires parameters in the format 'parameter/name = value'.
        Multiple parameters should be separated by newlines or semicolons.

        :param options: Solver options to apply
        :type options: SolverOptions
        """
        # Time limit - use native method (milliseconds)
        if options.time_limit is not None:
            time_limit_ms = int(options.time_limit.total_seconds() * 1000)
            self.solver.SetTimeLimit(time_limit_ms)

        # Build SCIP-format parameters
        param_parts = []

        if not options.presolve:
            param_parts.append("presolving/maxrounds = 0")

        if options.duality_gap is not None:
            param_parts.append(f"limits/gap = {options.duality_gap}")

        # Apply string parameters with newline separator for SCIP
        if param_parts:
            param_string = "\n".join(param_parts)
            self.solver.SetSolverSpecificParametersAsString(param_string)


class GenericParameterBuilder(SolverParameterBuilder):
    """
    Generic parameter builder for non-XPRESS solvers.

    Uses OR-Tools native methods when available.
    """

    def apply_options(self, options: SolverOptions) -> None:
        """Apply options using generic OR-Tools interface."""

        # Time limit - use native method (milliseconds)
        if options.time_limit is not None:
            # Convert Duration to milliseconds
            time_limit_ms = int(options.time_limit.total_seconds() * 1000)
            self.solver.SetTimeLimit(time_limit_ms)

        # Build string parameters
        param_parts = []

        if not options.presolve:
            param_parts.append("presolve off")
        else:
            param_parts.append("presolve on")

        if options.duality_gap is not None:
            param_parts.append(f"relative_mip_gap {options.duality_gap}")

        # Apply string parameters
        if param_parts:
            param_string = " ".join(param_parts)
            self.solver.SetSolverSpecificParametersAsString(param_string)
