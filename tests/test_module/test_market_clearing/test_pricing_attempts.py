"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Unit tests for the three-attempt sequencing of `Pricing.compute`: each attempt is only built when
the previous one failed, and a run where none of them succeeds must fail loudly rather than report
the solver's default zeros as market prices (issue #364).

As in `test_phases_unit.py`, `Pricing.compute` is exercised via the unbound-method technique against
a duck-typed stand-in, since `Pricing.__init__` otherwise requires a live OR-Tools model.
"""

from pathlib import Path

import pytest

from atlas.custom_errors import SolverError
from atlas.enums import SolverStatus
from atlas.modules.market_clearing.phases.pricing import Pricing
from atlas.solver.models import SolutionInfo


class _FakeModel:
    """Stand-in for the `OptimisationModel` composed by `Pricing`, replaying canned solve statuses."""

    def __init__(self, statuses: list[SolverStatus]):
        self._statuses = list(statuses)
        self.solve_count = 0

    def solve(self) -> SolutionInfo:
        self.solve_count += 1
        return SolutionInfo(status=self._statuses.pop(0))


class _FakeSolverParameters:
    export_lp = False


class _FakeParameters:
    solver = _FakeSolverParameters()

    def get_lp_dir(self) -> Path:
        return Path("unused")


class _PricingAttempts:
    """Duck-typed stand-in for `Pricing` exposing only what `compute` touches."""

    def __init__(self, statuses: list[SolverStatus]):
        self.model = _FakeModel(statuses)
        self.parameters = _FakeParameters()
        self.built: list[str] = []

    def build_first(self) -> None:
        self.built.append("first")

    def build_second(self) -> None:
        self.built.append("second")

    def build_third(self) -> None:
        self.built.append("third")

    def get_market_prices(self) -> dict:
        return {}

    def compute(self) -> None:
        return Pricing.compute(self)  # type: ignore[arg-type]


class TestPricingAttempts:
    """`Pricing.compute` — attempt sequencing and failure reporting."""

    def test_a_successful_first_attempt_stops_there(self):
        pricing = _PricingAttempts([SolverStatus.OPTIMAL])

        pricing.compute()

        assert pricing.built == ["first"]
        assert pricing.model.solve_count == 1

    def test_a_failed_first_attempt_falls_back_to_the_second(self):
        pricing = _PricingAttempts([SolverStatus.INFEASIBLE, SolverStatus.FEASIBLE])

        pricing.compute()

        assert pricing.built == ["first", "second"]

    def test_a_failed_second_attempt_falls_back_to_the_third(self):
        pricing = _PricingAttempts([SolverStatus.INFEASIBLE, SolverStatus.INFEASIBLE, SolverStatus.OPTIMAL])

        pricing.compute()

        assert pricing.built == ["first", "second", "third"]

    def test_all_attempts_failing_raises_instead_of_pricing_at_zero(self):
        pricing = _PricingAttempts([SolverStatus.INFEASIBLE, SolverStatus.INFEASIBLE, SolverStatus.UNBOUNDED])

        with pytest.raises(SolverError) as excinfo:
            pricing.compute()

        assert pricing.built == ["first", "second", "third"]
        assert "INFEASIBLE, INFEASIBLE, UNBOUNDED" in str(excinfo.value)
