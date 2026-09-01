"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas.common.optimal_dispatch.marginal_pricing import InterpolatedMarginalValue

TIME = pendulum.datetime(2026, 1, 1, 8)


class _Curve:
    """Stub timeseries returning a constant marginal value, ignoring time."""

    def __init__(self, value: float) -> None:
        self.value = value

    def get_value(self, _time) -> float:
        return self.value


class _Matrix:
    """Stub scenario matrix mapping a storage level (str index) to its marginal-value curve."""

    def __init__(self, curves: dict[str, float]) -> None:
        self._curves = curves

    @property
    def index(self) -> list[str]:
        return list(self._curves)

    def select(self, index: str) -> _Curve:
        return _Curve(self._curves[index])


def test_interpolates_between_bracketing_levels():
    # level 130 sits 70% of the way from 200 toward 100 -> 0.7*45 + 0.3*25
    matrix = _Matrix({"100": 45.0, "200": 25.0})
    marginal_value = InterpolatedMarginalValue.at_level(matrix, 130)
    assert marginal_value.value_at(TIME) == 39.0


def test_above_table_uses_highest_level_flat():
    matrix = _Matrix({"100": 45.0, "200": 25.0})
    marginal_value = InterpolatedMarginalValue.at_level(matrix, 250)
    assert marginal_value.value_at(TIME) == 25.0


def test_below_table_uses_lowest_level_flat():
    matrix = _Matrix({"100": 45.0, "200": 25.0})
    marginal_value = InterpolatedMarginalValue.at_level(matrix, 50)
    assert marginal_value.value_at(TIME) == 45.0


def test_empty_table_is_zero():
    marginal_value = InterpolatedMarginalValue.at_level(_Matrix({}), 130)
    assert marginal_value.value_at(TIME) == 0.0
