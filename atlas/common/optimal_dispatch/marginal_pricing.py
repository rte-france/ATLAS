"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.

Hydro bid curve: fragment volumes, and their pricing from storage marginal values
(a.k.a. *water values*).

A hydro unit bids energy as piecewise-linear *fragments*. Each fragment takes a share of
the unit's capacity (:func:`bid_volumes`), and its effective price is its base price plus
the marginal value of the water it consumes, evaluated at the reservoir's current energy
level. That marginal value comes from the unit's ``storage_marginal_value`` table (one
curve per discrete storage level) and is **linearly interpolated** between the two table
levels bracketing the current energy level.

Shared by the day-ahead orders, intraday orders and portfolio optimisation modules;
``HydroDispatch`` deliberately leaves this to the caller.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pendulum import DateTime

    from atlas.math.abstract_scenario_matrix import AbstractScenarioMatrix
    from atlas.math.abstract_timeseries import AbstractTimeseries
    from atlas.objects.equipment.hydro import FragmentData, Hydro


def bid_volumes(fragments: dict[int, FragmentData], capacity: float, minimal_fragment_size: float) -> dict[int, float]:
    """Split *capacity* across *fragments*, dropping the ones too small to bid.

    Each fragment takes its share of *capacity*; fragments landing below
    *minimal_fragment_size* are dropped and their volume is redistributed over the
    remaining ones, so the unit still offers its full capacity. When every fragment is too
    small, the whole capacity is bid as a single one instead.

    :param fragments: The unit's fragments, as given by ``Hydro.fragment_data``
    :param capacity: Power available at the timestamp being bid
    :param minimal_fragment_size: Smallest volume worth submitting as an order
    :return: Volume per fragment category, keyed as *fragments*

    :example:

    With fragment volumes ``[0.05, 0.25, 0.7]`` and a capacity of 100 MW, a minimal size
    of 10 MW drops the 5 MW fragment and spreads it over the other two::

        {1: 26.3, 2: 73.7}

    Raising the minimal size above 70 MW drops them all, leaving ``{2: 100}``.
    """
    volumes = {category: capacity * fragment.volume for category, fragment in fragments.items()}
    dropped = {category for category, volume in volumes.items() if volume < minimal_fragment_size}

    if sum(volumes[category] for category in dropped) <= 0:
        return volumes

    kept_capacity = sum(volume for category, volume in volumes.items() if category not in dropped)
    if kept_capacity == 0:
        # ponytail: index inherited from the day-ahead module — just above the middle, and
        # clamped because a single-fragment unit has no category 1.
        return {min(math.ceil(len(volumes) / 2), len(volumes) - 1): capacity}
    return {
        category: capacity * volume / kept_capacity for category, volume in volumes.items() if category not in dropped
    }


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
    energy_level: float = 0.0

    @classmethod
    def for_unit(
        cls,
        equipment: Hydro,
        execution_date: DateTime,
        initial_time: DateTime,
        cached_forecast: AbstractTimeseries | None = None,
    ) -> InterpolatedMarginalValue:
        """Price *equipment*'s water at the reservoir level it is expected to start from.

        The level comes from the unit's ``stored_energy`` forecast, as anticipated at
        *execution_date*, and falls back to its ``initial_level`` when there is no forecast
        or it does not cover *initial_time* — the timestep preceding the optimisation
        horizon. It stays readable afterwards as :attr:`energy_level`.

        Pass *cached_forecast* to reuse a forecast already fetched for the same
        *initial_time* (portfolio optimisation prefetches one per unit); the result is
        otherwise identical.
        """
        forecast = cached_forecast
        if forecast is None and equipment.stored_energy is not None:
            forecast = equipment.stored_energy.get_forecast(execution_date, initial_time, initial_time)

        if forecast is not None and initial_time in forecast:
            energy_level = forecast.get_value(initial_time)
        else:
            energy_level = equipment.initial_level.get_value(initial_time)  # type: ignore[union-attr]

        return cls.at_level(equipment.storage_marginal_value, energy_level)  # type: ignore[arg-type]

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
                energy_level=energy_level,
            )
        return cls(lower=lower, upper=upper, energy_level=energy_level)

    def value_at(self, time: DateTime) -> float:
        """Marginal value at *time*, interpolated between the bracketing storage levels."""
        if self.lower is None and self.upper is None:
            return 0.0
        if self.lower is None:
            return self.upper.get_value(time)  # type: ignore[union-attr]
        if self.upper is None:
            return self.lower.get_value(time)
        return self.lower_weight * self.lower.get_value(time) + self.upper_weight * self.upper.get_value(time)
