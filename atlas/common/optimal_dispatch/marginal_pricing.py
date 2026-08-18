"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Hydro fragment pricing from storage marginal values (a.k.a. *water values*).

A hydro unit bids energy as piecewise-linear *fragments*. The effective bid price of a
fragment is its base price plus the marginal value of the water it consumes, evaluated at
the reservoir's current energy level. That marginal value comes from the unit's
``storage_marginal_value`` table (one curve per discrete storage level) and is **linearly
interpolated** between the two table levels bracketing the current energy level.

Shared by the day-ahead orders and portfolio optimisation modules; ``HydroDispatch``
deliberately leaves this pricing to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
    from atlas.math.abstract_timeseries import AbstractTimeseries


@dataclass(frozen=True)
class InterpolatedMarginalValue:
    """Storage marginal value (water value) interpolated at a reservoir energy level.

    Built from the two ``storage_marginal_value`` rows bracketing the energy level:
    ``lower`` is the curve at the storage level just below, ``upper`` just above. When the
    energy level falls outside the table, only one side exists and its curve is used as-is
    (flat extrapolation); with an empty table both are ``None`` and the value is zero.
    """

    lower: AbstractTimeseries | None
    upper: AbstractTimeseries | None
    lower_weight: float = 0.0
    upper_weight: float = 0.0

    @classmethod
    def at_level(cls, storage_marginal_value: AbstractScenarioMatrix, energy_level: float) -> InterpolatedMarginalValue:
        """Bracket *energy_level* between the two adjacent storage levels and weight them."""
        levels = storage_marginal_value.index
        below = [level for level in levels if int(level) <= energy_level]
        above = [level for level in levels if int(level) > energy_level]

        lower_level = max(below, key=int) if below else None
        upper_level = min(above, key=int) if above else None

        lower = storage_marginal_value.select(lower_level) if lower_level is not None else None
        upper = storage_marginal_value.select(upper_level) if upper_level is not None else None

        if lower_level is not None and upper_level is not None:
            span = int(upper_level) - int(lower_level)
            return cls(
                lower=lower,
                upper=upper,
                lower_weight=(int(upper_level) - energy_level) / span,
                upper_weight=(energy_level - int(lower_level)) / span,
            )
        return cls(lower=lower, upper=upper)

    def value_at(self, time: DateTime) -> float:
        """Marginal value at *time*, interpolated between the bracketing storage levels."""
        if self.lower is None and self.upper is None:
            return 0.0
        if self.lower is None:
            return self.upper.get_value(time)  # type: ignore[union-attr]
        if self.upper is None:
            return self.lower.get_value(time)
        return self.lower_weight * self.lower.get_value(time) + self.upper_weight * self.upper.get_value(time)
