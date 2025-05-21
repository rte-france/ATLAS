"""Copyright (c) 2025, RTE (www.rte-france.com)

SPDX-License-Identifier: MPL-2.0
This file is part of the ATLAS project.
"""
from datetime import datetime

import pendulum
import pytest

from atlas.timing import to_pendulum_date


# Test for valid datetime strings
def test_valid_date_string():
    date_str = "20/05/2025 14:30:00"
    result = to_pendulum_date(date_str)
    assert isinstance(result, pendulum.DateTime)
    assert result == pendulum.datetime(2025, 5, 20, 14, 30)


# Test for invalid datetime string (should fall back to pendulum.parse)
def test_invalid_date_string():
    date_str = "2025-05-20"  # Missing time part
    result = to_pendulum_date(date_str)
    assert isinstance(result, pendulum.DateTime)
    assert result == pendulum.datetime(2025, 5, 20, 0, 0)  # Default time should be 00:00


# Test for valid datetime input
def test_valid_datetime_input():
    date_dt = datetime(2025, 5, 20, 14, 30)
    result = to_pendulum_date(date_dt)
    assert isinstance(result, pendulum.DateTime)
    assert result == pendulum.datetime(2025, 5, 20, 14, 30)


# Test for valid pendulum.DateTime input
def test_valid_datetime_object():
    date_pendulum_dt = pendulum.datetime(2025, 5, 20, 14, 30)
    result = to_pendulum_date(date_pendulum_dt)
    assert result is date_pendulum_dt  # It should return the same DateTime object


# Test for None input
def test_none_input():
    result = to_pendulum_date(None)
    assert result is None


def test_to_pendulum_date_invalid_string():
    with pytest.raises(ValueError, match="Unable to parse string"):
        to_pendulum_date("not a date")