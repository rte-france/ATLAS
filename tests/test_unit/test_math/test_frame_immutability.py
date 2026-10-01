"""
Pin the rule every math object relies on: polars frames are never mutated in place.

An ``inplace=True`` operation builds a new frame and rebinds the object to it; the frame the
object held before the call is left untouched. Copying a math object can therefore share its
frame instead of duplicating it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pendulum
import polars as pl
import pytest

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.lazy_matrix import LazyScenarioMatrix
from atlas.math.lazy_timeseries import LazyTimeseries
from atlas.math.matrix import ScenarioMatrix
from atlas.math.timeseries import Timeseries

TIMES = [datetime(2025, 1, 1, hour) for hour in range(4)]
LATER_TIMES = [datetime(2025, 1, 1, hour) for hour in range(4, 6)]


def _timeseries_frame(values: list[float], times: list[datetime] = TIMES) -> pl.DataFrame:
    return pl.DataFrame({"time": times, "value": values})


def _matrix_frame(indexes: list[str], lazy: bool) -> pl.DataFrame | pl.LazyFrame:
    columns = {index: [float(10 * i + hour) for hour in range(len(TIMES))] for i, index in enumerate(indexes)}
    frame = pl.DataFrame({"time": TIMES, **columns})
    return frame.lazy() if lazy else frame


def _collect(frame: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame:
    return frame.collect() if isinstance(frame, pl.LazyFrame) else frame


def _assert_previous_frame_untouched(obj: Any, operation: Callable[[Any], Any]) -> None:
    previous_frame = obj._get_data()
    expected = _collect(previous_frame).clone()

    operation(obj)

    assert _collect(previous_frame).equals(expected)


TIMESERIES_OPERATIONS: dict[str, Callable[[Any], Any]] = {
    "filter": lambda ts: ts.filter([TIMES[1]]),
    "slice": lambda ts: ts.slice(TIMES[1], TIMES[2]),
    "slice_with_offset": lambda ts: ts.slice_with_offset(1, 2),
    "abs": lambda ts: ts.abs(),
    "round": lambda ts: ts.round(),
    "clip": lambda ts: ts.clip(lower_bound=-15.0, upper_bound=35.0),
    "reindex": lambda ts: ts.reindex([TIMES[0], datetime(2025, 1, 1, 5)]),
    "add_on_union": lambda ts: ts.add_on_union(type(ts)(_timeseries_frame([1.0, 1.0, 1.0, 1.0]))),
    "set_frequency": lambda ts: ts.set_frequency(pendulum.duration(minutes=30)),
    "upsample": lambda ts: ts.upsample(pendulum.duration(minutes=30)),
    "groupby": lambda ts: ts.groupby(pendulum.duration(hours=2), "sum"),
    "set_value": lambda ts: ts.set_value(TIMES[1], 99.0),
    "set_values": lambda ts: ts.set_values(Timeseries(_timeseries_frame([98.0, 99.0], TIMES[1:3]))),
    "add_index": lambda ts: ts.add_index(datetime(2025, 1, 1, 4), 50.0),
    "add_indexes": lambda ts: ts.add_indexes(Timeseries(_timeseries_frame([50.0, 60.0], LATER_TIMES))),
    "sum_value_at": lambda ts: ts.sum_value_at(TIMES[1], 1.0),
    "mul_value_at": lambda ts: ts.mul_value_at(TIMES[1], 2.0),
    "interpolate": lambda ts: ts.interpolate(),
    "sort": lambda ts: ts.sort(),
    "set_timezone": lambda ts: ts.set_timezone("Europe/Paris"),
}


@pytest.mark.parametrize("timeseries_class", [Timeseries, LazyTimeseries])
@pytest.mark.parametrize("operation", TIMESERIES_OPERATIONS.values(), ids=TIMESERIES_OPERATIONS.keys())
def test_timeseries_operation_leaves_previous_frame_untouched(timeseries_class, operation):
    timeseries = timeseries_class(_timeseries_frame([-10.0, 20.0, None, 40.0]))

    _assert_previous_frame_untouched(timeseries, operation)


SCENARIO_INDEXES = ["scenario_1", "scenario_2"]
FORECAST_INDEXES = ["2025-01-01 00:00:00", "2025-01-01 01:00:00"]
NEW_FORECAST_INDEX = "2025-01-01 02:00:00"


def _matrix_operations(indexes: list[str], new_index: str) -> dict[str, Callable[[Any], Any]]:
    replacement = _timeseries_frame([1.0, 2.0, 3.0, 4.0])
    return {
        "abs": lambda matrix: matrix.abs(),
        "add": lambda matrix: matrix.add(Timeseries(replacement), new_index),
        "delete": lambda matrix: matrix.delete(indexes[0]),
        "replace": lambda matrix: matrix.replace(indexes[0], Timeseries(replacement)),
        "upsert": lambda matrix: matrix.upsert(indexes[0], Timeseries(replacement)),
        "set_frequency": lambda matrix: matrix.set_frequency(pendulum.duration(minutes=30)),
    }


SCENARIO_OPERATIONS = _matrix_operations(SCENARIO_INDEXES, "scenario_3")
FORECAST_OPERATIONS = _matrix_operations(FORECAST_INDEXES, NEW_FORECAST_INDEX)


@pytest.mark.parametrize("matrix_class", [ScenarioMatrix, LazyScenarioMatrix])
@pytest.mark.parametrize("operation", SCENARIO_OPERATIONS.values(), ids=SCENARIO_OPERATIONS.keys())
def test_scenario_matrix_operation_leaves_previous_frame_untouched(matrix_class, operation):
    matrix = matrix_class(_matrix_frame(SCENARIO_INDEXES, lazy=matrix_class is LazyScenarioMatrix))

    _assert_previous_frame_untouched(matrix, operation)


@pytest.mark.parametrize("matrix_class", [ForecastingMatrix, LazyForecastingMatrix])
@pytest.mark.parametrize("operation", FORECAST_OPERATIONS.values(), ids=FORECAST_OPERATIONS.keys())
def test_forecasting_matrix_operation_leaves_previous_frame_untouched(matrix_class, operation):
    matrix = matrix_class(_matrix_frame(FORECAST_INDEXES, lazy=matrix_class is LazyForecastingMatrix))

    _assert_previous_frame_untouched(matrix, operation)


def test_forecasting_matrix_set_date_format_leaves_previous_frame_untouched():
    matrix = ForecastingMatrix(_matrix_frame(FORECAST_INDEXES, lazy=False))

    _assert_previous_frame_untouched(matrix, lambda m: m.set_date_format("YYYY/MM/DD HH:mm:ss"))
