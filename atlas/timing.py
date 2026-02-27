"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Literal, cast

import pendulum
import polars as pl
import pytz


def datetime_to_pendulum(fmt: str) -> str:
    """Convert a datetime format string to a pendulum-compatible format string.

    :param fmt: The input format
    :type fmt: str
    """
    mapping = {
        "%Y": "YYYY",
        "%y": "YY",
        "%m": "MM",
        "%B": "MMMM",
        "%b": "MMM",
        "%d": "DD",
        "%H": "HH",
        "%I": "hh",
        "%p": "A",
        "%M": "mm",
        "%S": "ss",
        "%f": "SSSSSS",
        "%z": "Z",
        "%Z": "z",
        "%a": "ddd",
        "%A": "dddd",
        "%j": "DDDD",
        "%U": "ww",
        "%W": "ww",
        "%c": "llll",
        "%x": "ll",
        "%X": "LTS",
    }

    # Replace each token in format string
    for dt_token, pendulum_token in mapping.items():
        fmt = fmt.replace(dt_token, pendulum_token)

    return fmt


def pendulum_to_datetime(fmt: str) -> str:
    """Convert a pendulum-compatible format string to a datetime format string.

    :param fmt: The input format
    :type fmt: str
    """
    mapping = {
        "YYYY": "%Y",
        "YY": "%y",
        "MMMM": "%B",
        "MMM": "%b",
        "MM": "%m",
        "DD": "%d",
        "dddd": "%A",
        "ddd": "%a",
        "HH": "%H",
        "hh": "%I",
        "A": "%p",
        "mm": "%M",
        "ss": "%S",
        "SSSSSS": "%f",
        "Z": "%z",
        "z": "%Z",
        "DDDD": "%j",
        "ww": "%W",  # approximate
        "llll": "%c",
        "ll": "%x",
        "LTS": "%X",
    }

    # Sort keys longest-first to avoid partial replacement (e.g., 'MM' before 'M')
    for pendulum_token in sorted(mapping.keys(), key=lambda x: -len(x)):
        fmt = fmt.replace(pendulum_token, mapping[pendulum_token])

    return fmt


@contextmanager
def timer() -> Generator[Callable[[], str], None, None]:
    """Context manager to measure elapsed time with milliseconds precision."""
    start = pendulum.now()
    yield lambda: f"{(pendulum.now() - start).total_seconds():.3f}s"


def parse_frequency(freq: str) -> pendulum.Duration:
    """
    Parse a frequency string like '15m', '1h', or '1d30m' into a pendulum Duration object.

    :param freq: Frequency string to convert (e.g., '1d30m', '2h15m10s')
    :type freq: str
    :raises ValueError: If the frequency contains unsupported units or is malformed
    :return: A pendulum Duration object representing the frequency
    :rtype: pendulum.Duration
    """

    unit_map = {
        "y": "years",
        "M": "months",
        "w": "weeks",
        "d": "days",
        "h": "hours",
        "m": "minutes",
        "s": "seconds",
        "ms": "milliseconds",
        "us": "microseconds",
    }

    pattern = re.compile(r"(\d+)(ms|us|[yMwdhms])")
    matches = pattern.findall(freq)

    if not matches:
        raise ValueError(f"Unsupported or malformed frequency string: {freq}")

    duration_kwargs: dict[str, float] = {}
    for value, unit in matches:
        key = unit_map.get(unit, "")
        duration_kwargs[key] = duration_kwargs.get(key, 0) + int(value)

    return pendulum.duration(**duration_kwargs)


def build_datetime(dt: str | datetime | pendulum.DateTime, date_format="YYYY-MM-DD HH:mm:ss") -> pendulum.DateTime:
    """Converts a datetime string or object to pendulum datetime"""
    if isinstance(dt, str):
        return pendulum.from_format(dt, date_format)
    if isinstance(dt, datetime):
        return pendulum.instance(dt)
    if isinstance(dt, pendulum.DateTime):
        return dt
    raise TypeError(f"Unsupported type for dt: {type(dt)}. Expected str, datetime, or pendulum.DateTime.")


def generate_datetimes(
    start: str | datetime,
    end: str | datetime,
    freq: str | pendulum.Duration | timedelta,
    timezone: str = "UTC",
    date_format: str = "YYYY-MM-DD HH:mm:ss",
    closed: Literal["both", "left", "right", "none"] = "both",
) -> list[pendulum.DateTime]:
    """
    Generate a list of datetimes using pendulum.

    :param start: Start datetime
    :type start: datetime or str
    :param end: End datetime
    :type end: datetime or str
    :param freq: Frequency (e.g. "1h", "15m", "1d", "1w2d3h30m")
    :type freq: str
    :param timezone: Timezone string, defaults to "UTC"
    :type timezone: str, optional
    :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss"
    :type date_format: str, optional
    :param closed: Define which sides of the range are closed (inclusive).
    :type closed: {"both", "left", "right", "none"}
    :return: List of datetime objects
    :rtype: List[pendulum.DateTime]
    """
    start_date: pendulum.DateTime = build_datetime(start, date_format).in_tz(timezone)
    end_date: pendulum.DateTime = build_datetime(end, date_format).in_tz(timezone)

    if end_date < start_date:
        raise ValueError("End date has to be after start date")

    return [
        pendulum.instance(i)
        for i in pl.datetime_range(
            start=start_date.naive(),
            end=end_date.naive(),
            interval=get_duration(freq),
            closed=closed,
            time_unit="us",
            eager=True,
        )
        .dt.replace_time_zone(timezone)
        .to_list()
    ]


def get_duration(freq: str | timedelta | pendulum.Duration) -> pendulum.Duration:
    if isinstance(freq, str):
        step = parse_frequency(freq)
    elif isinstance(freq, pendulum.Duration):
        step = freq
    elif isinstance(freq, timedelta):
        step = pendulum.duration(seconds=freq.total_seconds())
    else:
        raise TypeError("Frequency must be a string, a timedelta or a pendulum.Duration")
    return step


def infer_frequency(timeseries: pl.DataFrame) -> pendulum.Duration:
    """
    Infer the frequency (timestep) as a pendulum.Duration.
    Returns None if the timeseries is empty or has only one timestamp.
    Raises ValueError if the index is not regular.
    """
    times = timeseries["time"]
    if len(times) < 2:
        return pendulum.duration()

    deltas_seconds = times.diff().dt.total_seconds().drop_nulls()

    first_delta = deltas_seconds[0]
    if not (deltas_seconds == first_delta).all():
        raise ValueError("Timeseries datetime index is not regular. Cannot infer frequency.")

    return pendulum.duration(seconds=first_delta)


def get_lowest_frequency(timeseries: pl.DataFrame) -> pendulum.Duration:
    times = timeseries["time"]
    if len(times) < 2:
        return pendulum.duration()

    min_delta_seconds = cast(float, times.diff().dt.total_seconds().drop_nulls().min())

    return pendulum.duration(seconds=min_delta_seconds)


def get_most_frequent_timestep(timeseries: pl.DataFrame) -> pendulum.Duration:
    """
    Compute the most frequent time delta between consecutive timestamps in the timeseries.

    :param timeseries: Polars DataFrame with a 'time' column (datetime or pendulum.DateTime)
    :return: The most frequent delta as pendulum.Duration
    :rtype: pendulum.Duration

    If there are multiple modes with the same count, the smallest delta is returned.
    If the timeseries has fewer than 2 timestamps, returns 0 duration.
    """
    times = timeseries["time"]
    if len(times) < 2:
        return pendulum.duration()

    mode_result = times.diff().dt.total_seconds().drop_nulls().mode()

    most_common_delta = mode_result.min() if len(mode_result) > 1 else mode_result[0]

    return pendulum.duration(seconds=cast(float, most_common_delta))


def check_timezone(timezone: str) -> None:
    """Validate timezone string."""
    if timezone not in pytz.all_timezones:
        raise ValueError(f"Invalid timezone: {timezone}")
