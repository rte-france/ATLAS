"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import re
from datetime import datetime

import pendulum


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


def parse_frequency(freq: str) -> pendulum.Duration:
    """
    Parse a frequency string like '15m', '1h', or '1d30m' into a pendulum Duration object.

    :param freq: Frequency string to convert (e.g., '1d30m', '2h15m10s')
    :type freq: str
    :raises ValueError: If the frequency contains unsupported units or is malformed
    :return: A pendulum Duration object representing the frequency
    :rtype: pendulum.Duration
    """
    # Map short unit suffixes to pendulum duration keyword arguments
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
        key = unit_map.get(unit)
        if not key:
            raise ValueError(f"Unsupported unit in frequency string: {unit}")
        duration_kwargs[key] = duration_kwargs.get(key, 0) + int(value)

    return pendulum.duration(**duration_kwargs)


def build_datetime(dt: str | datetime | pendulum.DateTime, date_format="YYYY-MM-DD HH:mm:ss") -> pendulum.DateTime:
    """Converts a datetime string or object to pendulum datetime"""
    return pendulum.from_format(dt, date_format) if isinstance(dt, str) else pendulum.instance(dt)


def generate_datetimes(
    start: str | datetime,
    end: str | datetime,
    freq: str | pendulum.Duration,
    timezone: str = "UTC",
    date_format: str = "YYYY-MM-DD HH:mm:ss z",
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
    :param date_format: Date format string, defaults to "YYYY-MM-DD HH:mm:ss z"
    :type date_format: str, optional
    :return: List of datetime objects
    :rtype: List[pendulum.DateTime]
    """
    start_date: pendulum.DateTime = build_datetime(start, date_format).in_tz(timezone)
    end_date: pendulum.DateTime = build_datetime(end, date_format).in_tz(timezone)

    if isinstance(freq, str):
        step = parse_frequency(freq)
    elif isinstance(freq, pendulum.Duration):
        step = freq
    else:
        raise ValueError("Frequency must be a string or a pendulum.Duration")
    return [start_date + i * step for i in range(int((end_date - start_date) / step) + 1)]
