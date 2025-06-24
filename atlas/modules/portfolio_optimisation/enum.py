"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from enum import Enum


class OptimizationMode(Enum):
    """Optimization modes for the portfolio."""

    PORTFOLIO_BIDDING = "portfolio"
    UNIT_BASED = "unit"


class SolverStatus(Enum):
    """Solver status enumeration."""

    OPTIMAL = "Optimal"
    INFEASIBLE = "Infeasible"
    UNBOUNDED = "Unbounded"
    TIME_LIMIT = "TimeLimit"
    ERROR = "Error"
