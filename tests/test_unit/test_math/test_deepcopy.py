"""Deep copies of math objects share their polars frame but nothing that can be mutated."""

from __future__ import annotations

import copy
from datetime import datetime

import polars as pl
import pytest

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_matrix import LazyScenarioMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries

TIMES = [datetime(2025, 1, 1, hour) for hour in range(4)]
INDEXES = ["2025-01-01 00:00:00", "2025-01-01 01:00:00"]


def _timeseries(lazy: bool) -> Timeseries | LazyTimeseries:
    frame = pl.DataFrame({"time": TIMES, "value": [1.0, 2.0, 3.0, 4.0]})
    return LazyTimeseries(frame) if lazy else Timeseries(frame)


def _matrix(matrix_class):
    frame = pl.DataFrame({"time": TIMES, **{index: [float(i)] * len(TIMES) for i, index in enumerate(INDEXES)}})
    return matrix_class(frame.lazy() if matrix_class in (LazyScenarioMatrix, LazyForecastingMatrix) else frame)


MATH_OBJECTS = [
    pytest.param(lambda: _timeseries(lazy=False), id="Timeseries"),
    pytest.param(lambda: _timeseries(lazy=True), id="LazyTimeseries"),
    pytest.param(lambda: _matrix(ScenarioMatrix), id="ScenarioMatrix"),
    pytest.param(lambda: _matrix(LazyScenarioMatrix), id="LazyScenarioMatrix"),
    pytest.param(lambda: _matrix(ForecastingMatrix), id="ForecastingMatrix"),
    pytest.param(lambda: _matrix(LazyForecastingMatrix), id="LazyForecastingMatrix"),
]


@pytest.mark.parametrize("build", MATH_OBJECTS)
def test_deepcopy_shares_the_frame(build):
    original = build()

    copied = copy.deepcopy(original)

    assert copied is not original
    assert type(copied) is type(original)
    assert copied._get_data() is original._get_data()


@pytest.mark.parametrize("build", MATH_OBJECTS)
def test_inplace_operation_on_a_deepcopy_leaves_the_original_untouched(build):
    original = build()
    frame = original._get_data()

    copied = copy.deepcopy(original)
    copied.set_frequency("30m")

    assert original._get_data() is frame
    assert copied._get_data() is not frame


@pytest.mark.parametrize("matrix_class", [ScenarioMatrix, LazyScenarioMatrix, ForecastingMatrix, LazyForecastingMatrix])
def test_deepcopy_does_not_share_the_indexes(matrix_class):
    original = _matrix(matrix_class)

    copied = copy.deepcopy(original)

    assert copied.indexes == original.indexes
    assert copied.indexes is not original.indexes


def test_deepcopy_of_a_timeseries_drops_its_lookup_cache():
    original = _timeseries(lazy=False)
    original._get_epoch_lookup()

    copied = copy.deepcopy(original)

    assert copied._epoch_lookup_cache is None
    assert copied._get_epoch_lookup() == original._get_epoch_lookup()


@pytest.mark.parametrize("matrix_class", [ForecastingMatrix, LazyForecastingMatrix])
def test_deepcopy_of_a_forecasting_matrix_gets_its_own_empty_cache(matrix_class):
    original = _matrix(matrix_class)
    original.get_forecast(TIMES[1], TIMES[0], TIMES[-1])

    copied = copy.deepcopy(original)

    assert copied._forecast_cache is not original._forecast_cache
    assert copied._forecast_cache._frame is None
    assert copied.get_forecast(TIMES[1], TIMES[0], TIMES[-1]) == original.get_forecast(TIMES[1], TIMES[0], TIMES[-1])


def test_deepcopy_keeps_shared_references_shared():
    timeseries = _timeseries(lazy=False)

    first, second = copy.deepcopy([timeseries, timeseries])

    assert first is second
    assert first is not timeseries
