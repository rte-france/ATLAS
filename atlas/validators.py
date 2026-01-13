"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""

from __future__ import annotations

from typing import Any

import pendulum
from pendulum.duration import Duration
from pydantic import ValidationError

from atlas.models.business_model import BusinessModel
from atlas.timing import parse_frequency


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


def serializer_list_float(value: list[float] | None) -> str | None:
    """Serialize list attributes to string."""
    if value is None:
        return None
    if isinstance(value, list):
        return ":".join(map(str, value))
    raise ValidationError(
        f"Expected list of floats, got: {value}",
    )


def serializer_business_model(value: BusinessModel | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, BusinessModel):
        return value.name
    raise ValidationError(
        f"Expected BusinessModel instance, got: {value}",
    )


def serializer_list_business_model(value: list[BusinessModel] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ":".join(str(bm.name) for bm in value)
    raise ValidationError(
        f"Expected list of floats, got: {value}",
    )


def convert_to_duration(
    value: Any,
    allow_zero: bool = True,
) -> pendulum.Duration | None:
    """
    Simple conversion of numeric values and Duration objects to Duration.

    Args:
        value: Input value to convert to Duration
        allow_zero: Whether to allow zero duration (negative values never allowed)

    Returns:
        Duration object or None if input is None

    Raises:
        ValueError: If input cannot be converted or validation fails

    Supported input formats:
        - None -> None
        - string like '15m', '1h', or '1d30m'
        - Duration as string using format iso_8601
        - Duration objects (both Pydantic and Pendulum) -> passthrough
    """
    if value is None:
        return None

    # Handle existing Duration objects
    if isinstance(value, Duration):
        duration_obj = value
    elif isinstance(value, str):
        if value == "P":
            duration_obj = pendulum.duration(hours=0)
            return duration_obj
        if value.startswith("P") or "T" in value:
            try:
                obj = pendulum.parse(value)
                if not isinstance(obj, Duration):
                    raise ValueError(f"Parsed value is not a Duration: {obj}")
                duration_obj = obj
            except Exception as e:
                raise ValueError(f"Failed to parse ISO 8601 duration string '{value}': {e}") from e
        else:
            duration_obj = parse_frequency(value)
    else:
        raise ValueError(
            f"Cannot convert {type(value).__name__} to Duration. "
            f"Supported types: None, str, Duration objects. Got: {value}"
        )

    # Validation - negative values never allowed for time durations
    total_seconds = duration_obj.total_seconds()

    if total_seconds < 0:
        raise ValueError(f"Negative duration not allowed: {duration_obj}")

    if not allow_zero and total_seconds == 0:
        raise ValueError(f"Zero duration not allowed: {duration_obj}")

    return duration_obj
