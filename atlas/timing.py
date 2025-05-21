"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from datetime import datetime
from typing import Annotated

import pendulum
from pendulum import DateTime
from pydantic import BeforeValidator

from atlas.config import logger


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


def to_pendulum_date(date: str | DateTime | datetime | None) -> DateTime | None:
    date_format = "DD/MM/YYYY HH:mm:ss"
    if isinstance(date, str):
        try:
            return pendulum.from_format(date, date_format)
        except ValueError:
            logger.exception(f"{date} doesn't not match {date_format}")
            pendulum_date = pendulum.parse(date)
            if isinstance(pendulum_date, DateTime):
                return pendulum_date
            else:
                logger.exception(f"{date} doesn't not match {date_format}")
    elif isinstance(date, datetime):
        return pendulum.instance(date)
    elif isinstance(date, DateTime):
        return date
    return None


datetime_type = Annotated[DateTime, BeforeValidator(to_pendulum_date)]
