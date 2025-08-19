import pytest
from pendulum import duration

from atlas.validators import convert_to_duration, hours_validator, minutes_validator


def test_basic_conversions():
    """Test basic number to duration conversions."""
    # Hours (default)
    result = convert_to_duration(2)
    assert result.total_seconds() == 7200  # 2 hours

    # Minutes
    result = convert_to_duration(30, default_unit="minutes")
    assert result.total_seconds() == 1800  # 30 minutes

    # Seconds
    result = convert_to_duration(90, default_unit="seconds")
    assert result.total_seconds() == 90


def test_none_and_zero():
    """Test None and zero inputs."""
    assert convert_to_duration(None) is None
    assert convert_to_duration(0).total_seconds() == 0


def test_duration_objects():
    """Test that duration objects pass through."""
    dur = duration(hours=1, minutes=30)
    result = convert_to_duration(dur)
    assert result.total_seconds() == dur.total_seconds()


def test_errors():
    """Test error cases."""
    # Negative values
    with pytest.raises(ValueError):
        convert_to_duration(-1)

    # Zero not allowed
    with pytest.raises(ValueError):
        convert_to_duration(0, allow_zero=False)

    # Invalid types
    with pytest.raises(ValueError):
        convert_to_duration("not a number")

    # Invalid unit
    with pytest.raises(ValueError):
        convert_to_duration(5, default_unit="days")


def test_validators():
    """Test the validator functions."""
    # Hours validator
    result = hours_validator(2.5)
    assert result.total_seconds() == 9000  # 2.5 hours

    # Minutes validator
    result = minutes_validator(45)
    assert result.total_seconds() == 2700  # 45 minutes

    # None handling
    assert hours_validator(None) is None
