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
IMMUTABLE_TYPES = (type(None), bool, int, float, str, datetime)


def _timeseries(timeseries_class):
    return timeseries_class(pl.DataFrame({"time": TIMES, "value": [1.0, 2.0, 3.0, 4.0]}))


def _matrix(matrix_class):
    frame = pl.DataFrame({"time": TIMES, **{index: [float(i)] * len(TIMES) for i, index in enumerate(INDEXES)}})
    return matrix_class(frame.lazy() if matrix_class in (LazyScenarioMatrix, LazyForecastingMatrix) else frame)


MATH_OBJECTS = [
    pytest.param(lambda: _timeseries(Timeseries), id="Timeseries"),
    pytest.param(lambda: _timeseries(LazyTimeseries), id="LazyTimeseries"),
    pytest.param(lambda: _matrix(ScenarioMatrix), id="ScenarioMatrix"),
    pytest.param(lambda: _matrix(LazyScenarioMatrix), id="LazyScenarioMatrix"),
    pytest.param(lambda: _matrix(ForecastingMatrix), id="ForecastingMatrix"),
    pytest.param(lambda: _matrix(LazyForecastingMatrix), id="LazyForecastingMatrix"),
]
# Lazy matrices cannot be built empty
EMPTY_MATH_OBJECTS = [
    pytest.param(Timeseries, id="empty-Timeseries"),
    pytest.param(LazyTimeseries, id="empty-LazyTimeseries"),
    pytest.param(ScenarioMatrix, id="empty-ScenarioMatrix"),
    pytest.param(ForecastingMatrix, id="empty-ForecastingMatrix"),
]


@pytest.mark.parametrize("build", MATH_OBJECTS + EMPTY_MATH_OBJECTS)
def test_deepcopy_shares_frames_and_copies_every_mutable_attribute(build):
    original = build()

    copied = copy.deepcopy(original)

    assert type(copied) is type(original)
    assert copied is not original
    assert vars(copied).keys() == vars(original).keys()
    for name, value in vars(original).items():
        if isinstance(value, (pl.DataFrame, pl.LazyFrame)):
            assert vars(copied)[name] is value, f"{name} should be shared"
        elif not isinstance(value, IMMUTABLE_TYPES):
            assert vars(copied)[name] is not value, f"{name} should be copied"
            # Caches start empty in the copy, see the dedicated tests below
            if not name.endswith("_cache"):
                assert vars(copied)[name] == value, f"{name} should be equal"


@pytest.mark.parametrize("build", MATH_OBJECTS)
def test_inplace_operation_on_a_deepcopy_leaves_the_original_untouched(build):
    original = build()
    frame = original._get_data()

    copied = copy.deepcopy(original)
    copied.set_frequency("30m")

    assert original._get_data() is frame
    assert copied._get_data() is not frame


@pytest.mark.parametrize("timeseries_class", [Timeseries, LazyTimeseries])
def test_deepcopy_of_a_timeseries_drops_its_lookup_cache(timeseries_class):
    original = _timeseries(timeseries_class)
    original._get_epoch_lookup()

    copied = copy.deepcopy(original)

    assert copied._epoch_lookup_cache is None
    assert copied._get_epoch_lookup() == original._get_epoch_lookup()


@pytest.mark.parametrize("matrix_class", [ForecastingMatrix, LazyForecastingMatrix])
def test_deepcopy_of_a_forecasting_matrix_gets_its_own_empty_cache(matrix_class):
    original = _matrix(matrix_class)
    original.get_forecast(TIMES[1], TIMES[0], TIMES[-1])

    copied = copy.deepcopy(original)

    assert copied._forecast_cache._frame is None
    assert copied.get_forecast(TIMES[1], TIMES[0], TIMES[-1]) == original.get_forecast(TIMES[1], TIMES[0], TIMES[-1])


def test_deepcopy_keeps_shared_references_shared():
    timeseries = _timeseries(Timeseries)

    first, second = copy.deepcopy([timeseries, timeseries])

    assert first is second
    assert first is not timeseries
