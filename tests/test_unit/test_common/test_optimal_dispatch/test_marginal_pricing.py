"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import pendulum

from atlas.common.optimal_dispatch.marginal_pricing import InterpolatedMarginalValue, bid_volumes
from atlas.objects.equipment.hydro import FragmentData

TIME = pendulum.datetime(2026, 1, 1, 8)
OTHER_TIME = pendulum.datetime(2026, 1, 1, 9)
EXECUTION_DATE = pendulum.datetime(2025, 12, 31, 12)


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


class _Levels:
    """Stub timeseries holding explicit values per time, so absence is observable."""

    def __init__(self, values: dict) -> None:
        self._values = values

    def __contains__(self, time) -> bool:
        return time in self._values

    def get_value(self, time) -> float:
        return self._values[time]


class _StoredEnergy:
    """Stub forecasting matrix recording the window it was asked for."""

    def __init__(self, forecast: _Levels) -> None:
        self.forecast = forecast
        self.calls: list[tuple] = []

    def get_forecast(self, execution_date, start, end) -> _Levels:
        self.calls.append((execution_date, start, end))
        return self.forecast


class _Unit:
    """Stub hydro unit exposing only the fields :meth:`for_unit` reads."""

    def __init__(self, stored_energy, initial_level) -> None:
        self.stored_energy = stored_energy
        self.initial_level = initial_level
        self.storage_marginal_value = _Matrix({"100": 45.0, "200": 25.0})


def test_energy_level_comes_from_the_forecast():
    stored_energy = _StoredEnergy(_Levels({TIME: 130.0}))
    unit = _Unit(stored_energy, _Levels({TIME: 250.0}))
    marginal_value = InterpolatedMarginalValue.for_unit(unit, EXECUTION_DATE, TIME)
    assert marginal_value.energy_level == 130.0
    assert marginal_value.value_at(TIME) == 39.0
    assert stored_energy.calls == [(EXECUTION_DATE, TIME, TIME)]


def test_energy_level_falls_back_without_stored_energy():
    unit = _Unit(None, _Levels({TIME: 250.0}))
    assert InterpolatedMarginalValue.for_unit(unit, EXECUTION_DATE, TIME).energy_level == 250.0


def test_energy_level_falls_back_when_forecast_misses_the_time():
    unit = _Unit(_StoredEnergy(_Levels({OTHER_TIME: 130.0})), _Levels({TIME: 250.0}))
    assert InterpolatedMarginalValue.for_unit(unit, EXECUTION_DATE, TIME).energy_level == 250.0


def test_cached_forecast_is_used_instead_of_refetching():
    stored_energy = _StoredEnergy(_Levels({TIME: 130.0}))
    unit = _Unit(stored_energy, _Levels({TIME: 250.0}))
    marginal_value = InterpolatedMarginalValue.for_unit(unit, EXECUTION_DATE, TIME, _Levels({TIME: 50.0}))
    assert marginal_value.energy_level == 50.0
    assert stored_energy.calls == []


def _fragments(volumes: list[float]) -> dict[int, FragmentData]:
    return {i: FragmentData(volume=v, price=float(i)) for i, v in enumerate(volumes)}


def test_fragments_take_their_share_of_capacity():
    assert bid_volumes(_fragments([0.25, 0.75]), capacity=100, minimal_fragment_size=10) == {0: 25.0, 1: 75.0}


def test_fragments_below_the_minimal_size_are_redistributed():
    # the 5 MW fragment is dropped, its volume spread over the two kept ones
    volumes = bid_volumes(_fragments([0.05, 0.25, 0.7]), capacity=100, minimal_fragment_size=10)
    assert sorted(volumes) == [1, 2]
    assert sum(volumes.values()) == 100.0


def test_full_capacity_goes_to_one_fragment_when_all_are_too_small():
    assert bid_volumes(_fragments([0.5, 0.5]), capacity=100, minimal_fragment_size=60) == {1: 100}
    assert bid_volumes(_fragments([0.2, 0.3, 0.5]), capacity=100, minimal_fragment_size=60) == {2: 100}


def test_single_fragment_unit_falls_back_on_its_only_category():
    assert bid_volumes(_fragments([1.0]), capacity=100, minimal_fragment_size=200) == {0: 100}


def test_zero_capacity_keeps_every_fragment_empty():
    # no volume to redistribute, so the minimal size must not trigger the single-fragment fallback
    assert bid_volumes(_fragments([0.5, 0.5]), capacity=0, minimal_fragment_size=10) == {0: 0.0, 1: 0.0}


def test_unit_without_fragments_bids_nothing():
    assert bid_volumes({}, capacity=100, minimal_fragment_size=10) == {}
