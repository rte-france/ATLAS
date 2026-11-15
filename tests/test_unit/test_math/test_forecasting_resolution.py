"""
Pin ForecastingMatrix.get_forecast against a reference implementation.

``_reference_get_forecast`` is the resolution algorithm as it was before forecasts were
memoised: it resolves the requested window from scratch on every call. Any optimisation of
``get_forecast`` must return exactly the same timeseries for every combination below.
"""

from __future__ import annotations

import itertools
from typing import cast

import pendulum
import polars as pl
import pytest

from atlas.math.forecasting_matrix import ForecastingMatrix, LazyForecastingMatrix
from atlas.math.timeseries import Timeseries
from atlas.timing import (
    build_datetime,
    generate_datetimes,
    get_duration,
    get_lowest_frequency,
    infer_frequency,
    pendulum_to_datetime,
)


def _column_frequency(df: pl.DataFrame, col: str) -> pendulum.Duration:
    col_df = df.select("time", col).drop_nulls()
    return infer_frequency(col_df) if col_df.height > 1 else pendulum.duration(hours=1)


def _reference_get_forecast(matrix, execution_date, start_date, end_date, timestep=None, default_value=None):
    execution_date = build_datetime(execution_date, matrix.date_format)
    start_date = build_datetime(start_date, matrix.date_format)
    end_date = build_datetime(end_date, matrix.date_format)

    if start_date > end_date:
        raise ValueError("Start date must be before end date")

    forecast_cols = (
        pl.DataFrame({"indexes_str": matrix.indexes})
        .with_columns(
            pl.col("indexes_str")
            .str.strptime(
                pl.Datetime(time_unit="us", time_zone=matrix.timezone),
                pendulum_to_datetime(matrix.date_format),
                strict=False,
            )
            .alias("indexes_dt")
        )
        .filter(pl.col("indexes_dt") <= execution_date)
        .sort("indexes_dt", descending=True)
        .select("indexes_str")
        .to_series()
        .to_list()
    )
    if not forecast_cols:
        raise ValueError("No forecasting dates available before execution date")

    df = matrix.matrix.select("time", *forecast_cols)
    frequency_target = get_duration(timestep) if timestep else get_lowest_frequency(df)
    limits = {col: _column_frequency(df, col) / frequency_target for col in forecast_cols}

    max_time = df["time"].max()
    if end_date > max_time:
        dt = cast("pendulum.DateTime", max_time)
        last_row = df.filter(pl.col("time").eq(dt))
        column_wth_last_timestamp = next((col for col in forecast_cols if last_row[col][0] is not None), None)
        if column_wth_last_timestamp:
            frequency_columns_last_timestamp = _column_frequency(df, column_wth_last_timestamp)
            if frequency_target < frequency_columns_last_timestamp:
                datetimes_to_add = generate_datetimes(
                    start=dt,
                    end=dt + frequency_columns_last_timestamp - frequency_target,
                    freq=frequency_target,
                    timezone=matrix.timezone,
                )
                if len(datetimes_to_add) > 1:
                    new_df = pl.DataFrame(
                        {
                            "time": datetimes_to_add[1:],
                            column_wth_last_timestamp: [None] * len(datetimes_to_add[1:]),
                        },
                        schema={"time": pl.Datetime("us", matrix.timezone), column_wth_last_timestamp: pl.Float64()},
                    )
                    df = pl.concat([df, new_df], how="diagonal")

    interpolate_expr = [pl.col(col).forward_fill(limit=int(limits[col])) for col in forecast_cols if limits[col] > 1]
    df = (
        df.upsample("time", every=frequency_target)
        .with_columns(interpolate_expr)
        .filter(pl.col("time").is_between(start_date, end_date))
        .select(pl.col("time"), pl.coalesce([pl.col(col) for col in forecast_cols]).alias("forecast"))
    )

    if default_value is not None:
        full_index = pl.DataFrame(
            {
                "time": generate_datetimes(
                    start=start_date, end=end_date, freq=frequency_target, timezone=matrix.timezone
                )
            }
        )
        df = full_index.join(df, on="time", how="left").with_columns(pl.col("forecast").fill_null(default_value))

    return Timeseries(df, timezone=matrix.timezone)


def _ts(start: pendulum.DateTime, freq: str, values: list[float], timezone: str = "UTC") -> Timeseries:
    ts = Timeseries.from_values(start, freq, values)
    ts.set_timezone(timezone)
    return ts


def _utc_matrix() -> ForecastingMatrix:
    """Three forecasts with different steps and spans, the oldest one being the longest."""
    day = pendulum.datetime(2025, 1, 1)
    matrix = ForecastingMatrix()
    matrix.add(_ts(day, "1h", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]), day)
    matrix.add(_ts(day.add(hours=1), "15m", [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0]), day.add(hours=1))
    matrix.add(_ts(day.add(hours=2), "30m", [21.0, 22.0, 23.0, 24.0]), day.add(hours=2))
    return matrix


def _paris_dst_matrix() -> ForecastingMatrix:
    """Hourly forecasts in Europe/Paris across the autumn DST change."""
    first = pendulum.datetime(2025, 10, 25, 22, tz="UTC")
    second = first.add(hours=5)  # 04:00 in Paris: index names must not fall in the repeated hour
    matrix = ForecastingMatrix(timezone="Europe/Paris")
    matrix.add(_ts(first, "1h", [float(i) for i in range(8)], "Europe/Paris"), first.in_tz("Europe/Paris"))
    matrix.add(_ts(second, "30m", [100.0 + i for i in range(6)], "Europe/Paris"), second.in_tz("Europe/Paris"))
    return matrix


def _windows(times: list[pendulum.DateTime]) -> list[tuple[pendulum.DateTime, pendulum.DateTime]]:
    """Point queries on every grid time, plus windows around and beyond the data."""
    first, last = times[0], times[-1]
    windows = [(t, t) for t in times]
    windows += [
        (first, last),
        (first.subtract(hours=2), first.add(hours=1)),
        (last.subtract(hours=1), last.add(hours=3)),
        (first.subtract(hours=3), last.add(hours=3)),
        (first.add(minutes=10), last.subtract(minutes=10)),
        (last.add(hours=1), last.add(hours=2)),
    ]
    return windows


def _cases(matrix: ForecastingMatrix, execution_dates: list[pendulum.DateTime]):
    times = [pendulum.instance(t).in_tz("UTC") for t in matrix.matrix["time"].to_list()]
    # built in UTC: a 15 min step in local time is ambiguous across the DST change
    steps = int((times[-1] - times[0]).total_seconds() // 900) + 5
    grid = [times[0].add(minutes=15 * i).in_tz(matrix.timezone) for i in range(steps)]
    for execution_date, (start, end), timestep, default_value in itertools.product(
        execution_dates, _windows(grid), [None, "15m", "30m", "1h"], [None, 0.0]
    ):
        yield execution_date, start, end, timestep, default_value


def _assert_same(matrix, reference_matrix, execution_date, start, end, timestep, default_value):
    try:
        expected = _reference_get_forecast(reference_matrix, execution_date, start, end, timestep, default_value)
    except Exception as error:
        # e.g. default_value across the autumn DST change: generate_datetimes cannot localise the repeated hour
        with pytest.raises(type(error)):
            matrix.get_forecast(execution_date, start, end, timestep, default_value)
        return
    result = matrix.get_forecast(execution_date, start, end, timestep, default_value)
    assert result.timezone == expected.timezone
    assert result.dataframe.equals(expected.dataframe), (execution_date, start, end, timestep, default_value)


MATRICES = {
    "utc": (
        _utc_matrix,
        [pendulum.datetime(2025, 1, 1, h, m) for h, m in [(0, 0), (1, 0), (1, 30), (2, 0), (12, 0)]],
    ),
    "paris_dst": (
        _paris_dst_matrix,
        [
            pendulum.datetime(2025, 10, 25, 22, tz="UTC").in_tz("Europe/Paris"),
            pendulum.datetime(2025, 10, 26, 3, 30, tz="UTC").in_tz("Europe/Paris"),
        ],
    ),
}


@pytest.mark.parametrize("name", MATRICES)
def test_get_forecast_matches_reference(name):
    build, execution_dates = MATRICES[name]
    matrix = build()
    for case in _cases(matrix, execution_dates):
        _assert_same(matrix, matrix, *case)


@pytest.mark.parametrize("name", MATRICES)
def test_lazy_get_forecast_matches_reference(name):
    build, execution_dates = MATRICES[name]
    matrix = build()
    lazy = LazyForecastingMatrix(matrix.matrix.lazy(), timezone=matrix.timezone, date_format=matrix.date_format)
    for case in _cases(matrix, execution_dates):
        _assert_same(lazy, matrix, *case)


def test_get_forecast_raises_like_reference():
    matrix = _utc_matrix()
    before_first = pendulum.datetime(2024, 12, 31, 23)
    with pytest.raises(ValueError, match="No forecasting dates"):
        matrix.get_forecast(before_first, before_first, before_first)
    start, end = pendulum.datetime(2025, 1, 1, 2), pendulum.datetime(2025, 1, 1, 1)
    with pytest.raises(ValueError, match="Start date must be before end date"):
        matrix.get_forecast(start, start, end)
