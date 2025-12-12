"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import Any

import pendulum
from pendulum import duration
from pendulum.duration import Duration
from pydantic import ValidationError


def parse_list_float(value: Any) -> list[float] | None:
    """Parse list attributes with proper error handling."""
    if value is None:
        return None
    if isinstance(value, list):
        if all(isinstance(v, float) for v in value):
            return value
        else:
            raise ValidationError(
                f"All elements in the list must be of type float. Got: {value}",
            )

    try:
        return list(map(float, value.split(":")))
    except Exception as e:
        raise ValidationError(
            f"Failed to parse list attribute '{value}': {e}",
        ) from e


def convert_to_duration(
    value: Any,
    default_unit: str = "hours",
    allow_zero: bool = True,
) -> pendulum.Duration | None:
    """
    Simple conversion of numeric values and Duration objects to Duration.

    Args:
        value: Input value to convert to Duration
        default_unit: Default unit for numeric values ("hours", "minutes", "seconds")
        allow_zero: Whether to allow zero duration (negative values never allowed)

    Returns:
        Duration object or None if input is None

    Raises:
        ValueError: If input cannot be converted or validation fails

    Supported input formats:
        - None -> None
        - int/float with default_unit (e.g., 2.5 -> 2.5 hours)
        - Duration objects (both Pydantic and Pendulum) -> passthrough
    """
    if value is None:
        return None

    # Handle existing Duration objects
    if isinstance(value, Duration):
        duration_obj = value
    elif isinstance(value, int | float):
        # Numeric value with default unit
        if default_unit == "hours":
            duration_obj = duration(hours=value)
        elif default_unit == "minutes":
            duration_obj = duration(minutes=value)
        elif default_unit == "seconds":
            duration_obj = duration(seconds=value)
        else:
            raise ValueError(f"Unsupported default_unit: {default_unit}")
    elif isinstance(value, str):
        if value == 'P':
            # pendulum.parse() fail to read 'P' which mean 0 duration in iso8601 format
            duration_obj = duration()
        else:
            duration_obj = pendulum.parse(value)
    else:
        raise ValueError(
            f"Cannot convert {type(value).__name__} to Duration. "
            f"Supported types: None, int, float, Duration objects. Got: {value}"
        )

    # Validation - negative values never allowed for time durations
    total_seconds = duration_obj.total_seconds()

    if total_seconds < 0:
        raise ValueError(f"Negative duration not allowed: {duration_obj}")

    if not allow_zero and total_seconds == 0:
        raise ValueError(f"Zero duration not allowed: {duration_obj}")

    return duration_obj


def duration_validator(
    default_unit: str = "hours",
    allow_zero: bool = True,
):
    """
    Factory function to create Pydantic field validators for Duration fields.

    Args:
        default_unit: Default unit for numeric inputs ("hours", "minutes", "seconds")
        allow_zero: Whether to allow zero duration (negative values never allowed)

    Returns:
        Validator function suitable for use with @field_validator

    Example:
        @field_validator('my_duration_field', mode='before')
        @classmethod
        def validate_duration(cls, v):
            return duration_validator(default_unit="minutes")(v)
    """

    def validator(value: Any) -> pendulum.Duration | None:
        return convert_to_duration(
            value,
            default_unit=default_unit,
            allow_zero=allow_zero,
        )

    return validator


# Common pre-configured validators
hours_validator = duration_validator(default_unit="hours")
minutes_validator = duration_validator(default_unit="minutes")
