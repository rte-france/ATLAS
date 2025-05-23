"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

import re

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

    duration_kwargs = {}
    for value, unit in matches:
        key = unit_map.get(unit)
        if not key:
            raise ValueError(f"Unsupported unit in frequency string: {unit}")
        duration_kwargs[key] = duration_kwargs.get(key, 0) + int(value)

    return pendulum.duration(**duration_kwargs)
